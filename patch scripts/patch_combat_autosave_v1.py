#!/usr/bin/env python3
r"""
Alternating combat autosaves (2026-11-04).

User: "keep the autosave at the beginning of each turn, but also do alternating autosaves after each combat (when
visible/shown in event log) ... called 'autosave - combat' and 'autosave - combat2'.  Different players will see
different combats in multiplayer, it's okay if their autosaves aren't the same but make sure it doesn't cause OoS."

Vanilla autosave = TPlayerControl.AutoSave 0x55755128 (VMT +0x58): non-campaign path builds
[AoWEngine+0x2C] + 'X\Save\' + 'autosave.asg' and calls AoWEngine VMT+0xAC (= HSEngine.THSEngine.SaveHSM, eax=engine,
edx=name, push 0, push 0) - a plain streaming save, local to this machine (the same call runs at every turn start).

  1. a tester: DistributeCombatEvent 0x5572928C adds a TCombatEventLog to every player who saw the battle
     (call TEventLogbook.Add 0x557FDB90 @0x5572932A, ebx = player index).  Wrapped: after the add, if ebx == the
     seated (local) player [AoWHSMap+0xA5] -> PENDING = 1.  Nothing about game state changes.
  2. Save: TAoWHSMap.NewFrame 0x55777CE8 inherited call @0x55777CEB wrapped: after it, if PENDING and no combat is
     running ([map+0x11C] == 0) and the seated player is not busy (TPlayer.GetBusy 0x557516D0 - moves / actions in
     progress) for 20 consecutive frames -> PENDING = 0 and save to 'X\Save\autosave - combat.asg' /
     'autosave - combat2.asg' (alternating, TOGGLE).  Campaign games ([map+0x11A] == 1, .acg autosaves) are skipped.
     Busy or combat frames reset the settle counter, so the save never runs mid-move or mid-battle.
OoS: the save only READS the game (same SaveHSM stream as the turn-start autosave); it runs on whichever machine saw
the combat, at its own time - no network message, no random-number use, no state written.
Position-independent (AoWEPACK can be rebased at runtime): every in-image address is ebp-relative from a call/pop.
State bytes in the unused AoWEPACK BSS tail: PENDING 0x558FAFE0, TOGGLE 0x558FAFE1, SETTLE dword 0x558FAFE4
(no code or script references 0x558FAFB0..0x558FAFFF - scanned 11/04).
Cave AoWEPACK 0x558E0E40..0x558E1000 'CAS1'.  Backup .bak_combatautosave.  Dry-run; --apply; --revert; --dis.
"""
import os, shutil, struct, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from bakpath import bak_path  # noqa: E402
import patch_sky_polish_v1 as SP  # noqa: E402
import sky_clouds_overlay_asm as OV  # noqa: E402

TAG = ".bak_combatautosave"
CAVE, CAVE_END, MAGIC = 0x558E0E40, 0x558E1000, b"CAS1"
HANDLE_ANY, DONE_EXCEPT = 0x557010E8, 0x55701108   # VCL30 thunks used by TPlayerControl.AutoSave's own try/except
MARK_SITE, MARK_ORIG, LOGBOOK_ADD = 0x5572932A, bytes.fromhex("e861480d00"), 0x557FDB90
NF_SITE, NF_ORIG, NF_INHERITED = 0x55777CEB, bytes.fromhex("8bc3e84ebaffff"), 0x55773740
G_MAP, G_ENGINE = 0x558FA040, 0x558FA048
PENDING, TOGGLE, SETTLE = 0x558FAFE0, 0x558FAFE1, 0x558FAFE4
PLAYER_GET, PLAYER_BUSY = 0x557544D0, 0x557516D0
SETTLE_FRAMES = 20
NAMES = [b"autosave - combat.asg", b"autosave - combat2.asg"]
SAVEDIR = b"X\\Save\\"


def src(at):
    """two entries, each starts with push ebp / call L / L: pop ebp  ->  ebp = entry + 6 (PIC base)"""
    mark_base = at + 6

    def r(base, target):
        return target - base

    mk = f"""
    mark:
        push ebp
        call mk_l
    mk_l:
        pop  ebp
        call {LOGBOOK_ADD:#x}
        mov  eax, dword ptr [ebp + {r(mark_base, G_MAP):#x}]
        movsx eax, byte ptr [eax + 0xa5]
        cmp  ebx, eax
        jne  mk_out
        mov  byte ptr [ebp + {r(mark_base, PENDING):#x}], 1
    mk_out:
        pop  ebp
        ret
    """
    mk_len = len(OV.asm(mk, at))
    nf_at = at + mk_len
    nf_base = nf_at + 6
    nf = f"""
    nf:
        push ebp
        call nf_l
    nf_l:
        pop  ebp
        mov  eax, ebx
        call {NF_INHERITED:#x}
        cmp  byte ptr [ebp + {r(nf_base, PENDING):#x}], 0
        je   nf_out
        cmp  dword ptr [ebx + 0x11c], 0
        jne  nf_reset
        movsx edx, byte ptr [ebx + 0xa5]
        test edx, edx
        jle  nf_reset
        mov  eax, dword ptr [ebx + 0x140]
        call {PLAYER_GET:#x}
        test eax, eax
        je   nf_reset
        call {PLAYER_BUSY:#x}
        test al, al
        jne  nf_reset
        inc  dword ptr [ebp + {r(nf_base, SETTLE):#x}]
        cmp  dword ptr [ebp + {r(nf_base, SETTLE):#x}], {SETTLE_FRAMES}
        jb   nf_out
        mov  byte ptr [ebp + {r(nf_base, PENDING):#x}], 0
        mov  dword ptr [ebp + {r(nf_base, SETTLE):#x}], 0
        cmp  byte ptr [ebx + 0x11a], 1
        je   nf_out
        call dosave
        jmp  nf_out
    nf_reset:
        mov  dword ptr [ebp + {r(nf_base, SETTLE):#x}], 0
    nf_out:
        pop  ebp
        ret

    dosave:
        push ebx
        push esi
        push edi
        sub  esp, 0x220
        mov  dword ptr [esp], 0xffffffff
        lea  edi, [esp + 8]
        mov  eax, dword ptr [ebp + {r(nf_base, G_ENGINE):#x}]
        mov  esi, dword ptr [eax + 0x2c]
        test esi, esi
        je   ds_dir
        mov  ecx, dword ptr [esi - 4]
        cmp  ecx, 0x1a0
        ja   ds_fail
        rep movsb
    ds_dir:
        lea  esi, [ebp + DIROFF]
        mov  ecx, {len(SAVEDIR)}
        rep movsb
        lea  esi, [ebp + NAME0OFF]
        mov  ecx, {len(NAMES[0])}
        cmp  byte ptr [ebp + {r(nf_base, TOGGLE):#x}], 0
        je   ds_nm
        lea  esi, [ebp + NAME1OFF]
        mov  ecx, {len(NAMES[1])}
    ds_nm:
        rep movsb
        mov  byte ptr [edi], 0
        lea  eax, [esp + 8]
        sub  edi, eax
        mov  dword ptr [esp + 4], edi
        xor  byte ptr [ebp + {r(nf_base, TOGGLE):#x}], 1
        xor  eax, eax                     ; v1.1 2026-11-16: Delphi try/except round the save - a locked file
        push ebp                          ; (two instances sharing one Save folder, antivirus ...) raised EFCreateError
        mov  ecx, ebp                     ; through NewFrame -> "Exception during AoWHSMap.NewFrame" pop-up
        add  ecx, ds_exc - nf_l
        push ecx
        push dword ptr fs:[eax]
        mov  dword ptr fs:[eax], esp
        push 0
        push 0
        lea  edx, [esp + 0x1c]
        mov  eax, dword ptr [ebp + {r(nf_base, G_ENGINE):#x}]
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx + 0xac]
        xor  eax, eax
        pop  edx
        pop  ecx
        pop  ecx
        mov  dword ptr fs:[eax], edx
        jmp  ds_fail
    ds_exc:
        jmp  {HANDLE_ANY:#x}              ; System.@HandleAnyException: unwinds, restores ebp, resumes below
        call {DONE_EXCEPT:#x}             ; System.@DoneExcept: frees the exception, pops our frame (ebp restored)
    ds_fail:
        add  esp, 0x220
        pop  edi
        pop  esi
        pop  ebx
        ret
    """
    return mk, nf, nf_at, nf_base


def build():
    at = CAVE + len(MAGIC)
    mk, nf, nf_at, nf_base = src(at)
    mk_code = OV.asm(mk, at)
    # strings go right after the nf code; two passes to learn their offsets
    tmp = OV.asm(nf.replace("DIROFF", "0x0").replace("NAME0OFF", "0x0").replace("NAME1OFF", "0x0"), nf_at)
    s_at = nf_at + len(tmp) + 32                    # disp8 -> disp32 growth margin
    dir_at = s_at
    n0_at = dir_at + len(SAVEDIR)
    n1_at = n0_at + len(NAMES[0])
    nf_code = OV.asm(nf.replace("DIROFF", hex(dir_at - nf_base)).replace("NAME0OFF", hex(n0_at - nf_base))
                     .replace("NAME1OFF", hex(n1_at - nf_base)), nf_at)
    assert nf_at + len(nf_code) <= s_at, "string area overlaps code"
    pad = bytes(s_at - (nf_at + len(nf_code)))
    blob = MAGIC + mk_code + nf_code + pad + SAVEDIR + NAMES[0] + NAMES[1]
    assert CAVE + len(blob) <= CAVE_END, hex(len(blob))
    return blob, at, nf_at


def patches():
    blob, mark_at, nf_at = build()
    return [(MARK_SITE, MARK_ORIG, b"\xe8" + struct.pack("<i", mark_at - (MARK_SITE + 5))),
            (NF_SITE, NF_ORIG, b"\xe8" + struct.pack("<i", nf_at - (NF_SITE + 5)) + b"\x90\x90"),
            (CAVE, bytes(len(blob)), blob)]


def main():
    import pefile
    apply = "--apply" in sys.argv; revert = "--revert" in sys.argv
    if "--dis" in sys.argv:
        from capstone import Cs, CS_ARCH_X86, CS_MODE_32
        blob, mark_at, nf_at = build()
        for i in Cs(CS_ARCH_X86, CS_MODE_32).disasm(blob[4:], CAVE + 4):
            print("  %08x %-20s %s %s" % (i.address, i.bytes.hex(), i.mnemonic, i.op_str))
        print("strings:", blob[blob.index(SAVEDIR):])
        return 0
    if (apply or revert) and SP.busy():
        print("game/editor running - close it first"); return 1
    d = open(SP.EPK, "rb").read(); pe = pefile.PE(data=d)
    P = patches()
    st, bad = SP.state(d, pe, SP.EBASE, P)
    print("AoWEPACK %s relocs %s" % (st, bad or "none"))
    if "OTHER" in st or bad or len(set(st)) != 1:
        print("ABORT"); return 1
    if revert:
        if st[0] == "ours":
            SP.write_bytes(SP.EPK, SP.EBASE, P, True); print("reverted")
        return 0
    if st[0] == "ours":
        print("already applied"); return 0
    if not apply:
        print("Dry run OK - rerun with --apply (or --revert)."); return 0
    bk = bak_path(SP.EPK, TAG)
    if not os.path.exists(bk):
        shutil.copy2(SP.EPK, bk)
    SP.write_bytes(SP.EPK, SP.EBASE, P, False)
    print("written and verified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
