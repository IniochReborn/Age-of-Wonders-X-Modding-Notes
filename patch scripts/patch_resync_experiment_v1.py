#!/usr/bin/env python3
r"""
EXPERIMENT (2026-11-16): in-place reload of a network game ("out of sync -> save and instant reload", option 2).
NOT a shipping feature - a test rig to find out whether every machine can swap its running map for the same save
while keeping the DirectPlay session, the seats and the token ring.

How a reload works here (per machine, at the exe's own safe point - the per-frame spot in the main frame routine
0x452AC8 where it acts on the 'exit game' flag [map+0x1C0], @0x4530D0):
  1. keep the live connection object: pcc = [[map+0x240]+0x1C] (TRemotePCC: per-player modes, system ids, local id,
     send callback) -> AddRef;   remember [map+0x13A] remote flag, +0x239 play mode, +0x14C/+0x149/+0x14A,
     +0x158/+0x15C, bit 4 of +0x3C  (what TSetupControl.SetupMap 0x557E0B64 writes from the lobby settings)
  2. exe MainWin.LoadMapFile 0x454B70 (eax = main window [[0x45A420]], edx = file): unloads the running map
     (engine VMT+0xB0) and loads the file (engine VMT+0xA4) - the routine the in-game "Load game" uses
  3. on the new map: restore the fields (incl. play mode +0x239), TPlayerCommunicator.ActivatePCC(pcc)
     ([map+0x240] VMT+0x4C), Release.  (v1.1: NO SetupPlayerControl call and do NOT copy bit 4 of [map+0x3C] - that
     bit is "map activated"; copying it made TAoWHSMap.Activate (called by StartGame; it runs SetupPlayerControl +
     token manager init itself) raise 'HSMap already activated' half-way, which also left the client seated as
     the host's player.)
  4. exe MainWin.StartGame 0x454D2C, then the chat refreshers 0x414424 / 0x41444C when connected
     (= what the lobby's 'game starts' handler 0x413A64 does).

  v3: unloading the old map fires the exe's TheMapDeactivateHSM handler (0x44EDDC), which calls TGDPlay.DisConnect
  (deferred: sets [TGDPlay+0x1F1]; CheckMessages closes DirectPlay on the next frame).  Runs 1-3 therefore ended
  with BOTH instances silently out of the session.  The reload now clears that flag right after LoadMapFile.

Trigger (test rig only; all instances share one game folder on the test PC): every 64 frames each instance looks at
<game>\X\Save\ :
  * resync.save exists and this instance is the DirectPlay host ([TGDPlay+0x1EF]) -> delete it, save the game to
    resync.asg (engine VMT+0xAC), then save again as marker resync.gNN (NN = this instance's generation + 1)
  * resync.gNN for generation+1 exists -> generation++ and reload resync.asg as above.
  Generations already present when an instance first polls are skipped.

Pieces: AoWEPACK cave 0x55856700.. (PIC; exe addresses absolute - the exe is never rebased), vars 0x558E9D20
(counter, generation, init) + path buffer 0x558E9D30..0x558E9DF0 (DATA tail, unreferenced);
exe: stub in the free tail of the indicator's part of .xedt (0x62F7C8, 20 B) + `call stub` over
`mov eax,[0x45DF7C]` @0x4530D0 (reloc 0x4530D1 neutralised).
Backups .bak_resyncx on AoWEPACK.dll and AoWx.exe.  Dry run by default; --apply / --revert.
"""
import argparse, os, shutil, struct, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file

EP, EP_V2F = game_file("AoWEPACK.dll"), 0x55700C00
EXE, EXE_V2F = game_file("AoWx.exe"), 0x400C00
BAK = ".bak_resyncx"
CAVE, CAVE_END = 0x55856700, 0x55856C00
VARS, BUF = 0x558E9D20, 0x558E9D30
MAPG, ENGINE = 0x558FA040, 0x558FA048
FILEEXISTS, DELETEFILE, RELEASE, RELEASE_SLOT = 0x557015A4, 0x5570146C, 0x557035D4, 0x558FCAD8
SETUPPC, SAVEGAME_VA = 0x55777F1C, 0x55775884
X_MAINWIN, X_DPLAY, X_LOAD, X_START, X_CHAT1, X_CHAT2 = 0x45A420, 0x45A454, 0x454B70, 0x454D2C, 0x414424, 0x41444C
X_SLOT_SAVEGAME, X_MAPVAR = 0x45DDB0, 0x45DF7C
# v4: "Waiting for other players" on the game's progress panel (the 'Transferring Files... / Please Wait' window of
# the lobby handler 0x4149D8: form [[0x45A24C]] +0x44 label, +0x50 label, +0x58 gauge, +0x54 panel; shown above
# everything with TAOWWinManager.SetOverPri([mainwin+0x44], 0x1388)) while frozen before and after the reload.
X_PROGRESS, X_SETOVERPRI, X_SETGTEXT, X_GAUGEPOS, X_STR_PLEASEWAIT = 0x45A24C, 0x40312C, 0x403254, 0x403980, 0x414A60
STUB_VA, STUB_FO = 0x62F7C8, 0x228600 + 0x7C8
HOOK_VA, HOOK_ORIG = 0x4530D0, bytes.fromhex("a17cdf4500")
RELOC_VA = 0x4530D1
# v2: freeze gate in TAoWHSMap.NewFrame - while FROZEN the AI executer and the token manager are not processed
# (incoming packets still queue).  marker seen -> FROZEN (3 polls) -> reload (still frozen, 4 polls) -> run.
NF_SITE, NF_ORIG, NF_BACK, NF_SKIP = 0x55777D0E, bytes.fromhex("83bb1c01000000"), 0x55777D15, 0x55777D36


def build_cave():
    from keystone import Ks, KS_ARCH_X86, KS_MODE_32
    src = f"""
    tick:
        call td
    td:
        pop ebx
        sub ebx, td
        mov esi, [ebx + {MAPG:#x}]
        test esi, esi
        jz t_out
        inc dword ptr [ebx + {VARS:#x}]
        test byte ptr [ebx + {VARS:#x}], 0x3f
        jnz t_out
        cmp byte ptr [ebx + {VARS + 8:#x}], 0
        jne t_state
        xor edi, edi
    t_scan:
        lea eax, [edi + 1]
        cmp eax, 99
        ja t_scanned
        call mkgen
        test eax, eax
        jz t_scanned
        call {FILEEXISTS:#x}
        test al, al
        jz t_scanned
        inc edi
        jmp t_scan
    t_scanned:
        mov [ebx + {VARS + 4:#x}], edi
        mov byte ptr [ebx + {VARS + 8:#x}], 1
        jmp t_out
    t_state:
        cmp byte ptr [ebx + {VARS + 10:#x}], 1
        je t_s1
        cmp byte ptr [ebx + {VARS + 10:#x}], 2
        je t_s2
        jmp t_run
    t_s1:
        inc byte ptr [ebx + {VARS + 11:#x}]
        cmp byte ptr [ebx + {VARS + 11:#x}], 3
        jb t_out
        mov edx, ebx
        add edx, s_asg
        call mkpath
        test eax, eax
        jz t_s1x
        call reload
        call show_wait
    t_s1x:
        mov byte ptr [ebx + {VARS + 10:#x}], 2
        mov byte ptr [ebx + {VARS + 11:#x}], 0
        jmp t_out
    t_s2:
        inc byte ptr [ebx + {VARS + 11:#x}]
        cmp byte ptr [ebx + {VARS + 11:#x}], 4
        jb t_out
        mov byte ptr [ebx + {VARS + 9:#x}], 0
        mov byte ptr [ebx + {VARS + 10:#x}], 0
        call hide_wait
        jmp t_out
    t_run:
        mov edx, ebx
        add edx, s_save
        call mkpath
        test eax, eax
        jz t_out
        mov edi, eax
        call {FILEEXISTS:#x}
        test al, al
        jz t_chk
        mov eax, [{X_DPLAY:#x}]
        mov eax, [eax]
        mov eax, [eax + 0x44]
        cmp byte ptr [eax + 0x1ef], 0
        je t_chk
        push edi
        call {DELETEFILE:#x}
        mov edx, ebx
        add edx, s_asg
        call mkpath
        call dosave
        mov eax, [ebx + {VARS + 4:#x}]
        inc eax
        call mkgen
        call dosave
    t_chk:
        mov eax, [ebx + {VARS + 4:#x}]
        inc eax
        cmp eax, 99
        ja t_out
        call mkgen
        test eax, eax
        jz t_out
        call {FILEEXISTS:#x}
        test al, al
        jz t_out
        inc dword ptr [ebx + {VARS + 4:#x}]
        mov byte ptr [ebx + {VARS + 9:#x}], 1
        mov byte ptr [ebx + {VARS + 10:#x}], 1
        mov byte ptr [ebx + {VARS + 11:#x}], 0
        call show_wait
    t_out:
        ret

    show_wait:
        mov eax, [{X_MAINWIN:#x}]
        mov eax, [eax]
        mov eax, [eax + 0x44]
        mov edx, 0x1388
        mov ecx, {X_SETOVERPRI:#x}
        call ecx
        mov eax, [{X_PROGRESS:#x}]
        mov eax, [eax]
        push eax
        mov eax, [eax + 0x44]
        mov edx, ebx
        add edx, s_wait
        mov ecx, {X_SETGTEXT:#x}
        call ecx
        mov eax, [esp]
        mov eax, [eax + 0x50]
        mov edx, {X_STR_PLEASEWAIT:#x}
        mov ecx, {X_SETGTEXT:#x}
        call ecx
        mov eax, [esp]
        mov eax, [eax + 0x58]
        xor edx, edx
        mov ecx, {X_GAUGEPOS:#x}
        call ecx
        pop eax
        mov eax, [eax + 0x54]
        mov dl, 1
        mov ecx, [eax]
        call dword ptr [ecx + 0x6c]
        ret

    hide_wait:
        mov eax, [{X_MAINWIN:#x}]
        mov eax, [eax]
        mov eax, [eax + 0x44]
        xor edx, edx
        mov ecx, {X_SETOVERPRI:#x}
        call ecx
        mov eax, [{X_PROGRESS:#x}]
        mov eax, [eax]
        mov eax, [eax + 0x54]
        xor edx, edx
        mov ecx, [eax]
        call dword ptr [ecx + 0x6c]
        ret

    nfgate:
        push eax
        call ng
    ng:
        pop eax
        sub eax, ng
        cmp byte ptr [eax + {VARS + 9:#x}], 0
        pop eax
        jne ng_skip
        cmp dword ptr [ebx + 0x11c], 0
        jmp {NF_BACK:#x}
    ng_skip:
        jmp {NF_SKIP:#x}

    dosave:                               ; eax = file name (AnsiString)
        push 0
        push 0
        mov edx, eax
        mov eax, [ebx + {ENGINE:#x}]
        mov ecx, [eax]
        call dword ptr [ecx + 0xac]
        ret

    mkpath:                               ; edx = suffix (C string) -> eax = AnsiString in BUF, 0 if too long
        push esi
        push edi
        lea edi, [ebx + {BUF + 8:#x}]
        mov eax, [ebx + {ENGINE:#x}]
        mov esi, [eax + 0x2c]
        test esi, esi
        jz mp_sfx
        mov ecx, [esi - 4]
        cmp ecx, 0x80
        ja mp_fail
        rep movsb
    mp_sfx:
        mov esi, edx
    mp_l:
        lodsb
        stosb
        test al, al
        jnz mp_l
        lea eax, [ebx + {BUF + 8:#x}]
        dec edi
        sub edi, eax
        mov [eax - 4], edi
        mov dword ptr [eax - 8], 0xffffffff
        pop edi
        pop esi
        ret
    mp_fail:
        xor eax, eax
        pop edi
        pop esi
        ret

    mkgen:                                ; eax = generation 1..99 -> eax = path of resync.gNN (or 0)
        push eax
        mov edx, ebx
        add edx, s_gen
        call mkpath
        pop ecx
        test eax, eax
        jz mg_out
        push eax
        mov edx, [eax - 4]
        lea edx, [eax + edx - 2]
        mov eax, ecx
        mov cl, 10
        div cl
        add ax, 0x3030
        mov [edx], al
        mov [edx + 1], ah
        pop eax
    mg_out:
        ret

    reload:                               ; eax = save file (AnsiString)
        push ebp
        mov ebp, esp
        sub esp, 0x20
        mov [ebp - 4], eax
        mov esi, [ebx + {MAPG:#x}]
        mov al, [esi + 0x13a]
        mov [ebp - 8], al
        mov al, [esi + 0x239]
        mov [ebp - 7], al
        mov al, [esi + 0x14c]
        mov [ebp - 6], al
        mov al, [esi + 0x149]
        mov [ebp - 5], al
        mov al, [esi + 0x14a]
        mov [ebp - 0x1c], al
        mov al, [esi + 0x3c]
        mov [ebp - 0x1b], al
        mov eax, [esi + 0x158]
        mov [ebp - 0xc], eax
        mov eax, [esi + 0x15c]
        mov [ebp - 0x10], eax
        xor edi, edi
        mov eax, [esi + 0x240]
        test eax, eax
        jz r_nopcc
        mov edi, [eax + 0x1c]
        test edi, edi
        jz r_nopcc
        mov eax, edi
        mov ecx, [ebx + {RELEASE_SLOT:#x}]
        sub ecx, 4                        ; TPlayerCommunicationControl.AddRef sits 4 bytes before .Release
        call ecx
    r_nopcc:
        mov [ebp - 0x14], edi
        mov eax, [{X_MAINWIN:#x}]
        mov eax, [eax]
        mov edx, [ebp - 4]
        mov ecx, {X_LOAD:#x}
        call ecx
        mov eax, [{X_DPLAY:#x}]
        mov eax, [eax]
        mov eax, [eax + 0x44]
        mov byte ptr [eax + 0x1f1], 0
        mov esi, [ebx + {MAPG:#x}]
        test esi, esi
        jz r_done
        mov al, [ebp - 8]
        mov [esi + 0x13a], al
        mov al, [ebp - 6]
        mov [esi + 0x14c], al
        mov al, [ebp - 5]
        mov [esi + 0x149], al
        mov al, [ebp - 0x1c]
        mov [esi + 0x14a], al
        mov eax, [ebp - 0xc]
        mov [esi + 0x158], eax
        mov eax, [ebp - 0x10]
        mov [esi + 0x15c], eax
        mov edi, [ebp - 0x14]
        test edi, edi
        jz r_spc
        mov eax, [esi + 0x240]
        test eax, eax
        jz r_rel
        mov edx, edi
        mov ecx, [eax]
        call dword ptr [ecx + 0x4c]
    r_rel:
        mov eax, edi
        call {RELEASE:#x}
    r_spc:
        mov al, [ebp - 7]
        mov [esi + 0x239], al
        mov eax, [{X_MAINWIN:#x}]
        mov eax, [eax]
        mov ecx, {X_START:#x}
        call ecx
        mov eax, [{X_DPLAY:#x}]
        mov eax, [eax]
        mov edx, [eax + 0x44]
        cmp byte ptr [edx + 0x1ed], 0
        je r_done
        push eax
        mov ecx, {X_CHAT1:#x}
        call ecx
        pop eax
        mov ecx, {X_CHAT2:#x}
        call ecx
    r_done:
        mov esp, ebp
        pop ebp
        ret

        .align 4
        .long 0xffffffff
        .long 25
    s_wait:
        .ascii "Waiting for other players"
        .byte 0
    s_save:
        .ascii "X\\\\Save\\\\resync.save"
        .byte 0
    s_asg:
        .ascii "X\\\\Save\\\\resync.asg"
        .byte 0
    s_gen:
        .ascii "X\\\\Save\\\\resync.g00"
        .byte 0
    """
    src = chr(10).join(l.split(";")[0].rstrip() for l in src.split(chr(10)))      # keystone: ";" separates statements
    code = bytes(Ks(KS_ARCH_X86, KS_MODE_32).asm(src, CAVE)[0])
    assert len(code) <= CAVE_END - CAVE, hex(len(code))
    assert b"X\\Save\\resync.g00\0" in code and b"\\\\" not in code, "string escapes"
    full = bytes(Ks(KS_ARCH_X86, KS_MODE_32).asm(src + chr(10) + ".long nfgate" + chr(10), CAVE)[0])
    return code, struct.unpack("<I", full[-4:])[0]


def stub():
    b = b"\x60" + b"\xa1" + struct.pack("<I", X_SLOT_SAVEGAME) + b"\x05" + struct.pack("<i", CAVE - SAVEGAME_VA) \
        + b"\xff\xd0" + b"\x61" + b"\xa1" + struct.pack("<I", X_MAPVAR) + b"\xc3"
    assert len(b) == 20
    return b


def reloc_entry(d, va):
    import pefile
    pe = pefile.PE(data=bytes(d), fast_load=True)
    pe.parse_data_directories([pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_BASERELOC"]])
    ib = pe.OPTIONAL_HEADER.ImageBase
    for blk in pe.DIRECTORY_ENTRY_BASERELOC:
        for e in blk.entries:
            if ib + e.rva == va:
                return e.struct.get_file_offset(), e.type
    return None, None


def relocs_in(path, lo, hi):
    import pefile
    pe = pefile.PE(path, fast_load=True)
    pe.parse_data_directories([pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_BASERELOC"]])
    ib = pe.OPTIONAL_HEADER.ImageBase
    return [hex(ib + e.rva) for blk in pe.DIRECTORY_ENTRY_BASERELOC for e in blk.entries if e.type and lo - 3 <= ib + e.rva < hi]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true"); ap.add_argument("--revert", action="store_true")
    ap.add_argument("--dis", action="store_true")
    a = ap.parse_args()
    (cave, nfgate), st = build_cave(), stub()
    nf_new = bytes([0xE9]) + struct.pack("<i", nfgate - (NF_SITE + 5)) + bytes([0x90, 0x90])
    if a.dis:
        import capstone
        for i in capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32).disasm(cave, CAVE):
            print("  %08X %-22s %s %s" % (i.address, i.bytes.hex(), i.mnemonic, i.op_str))
    e = bytearray(open(EP, "rb").read()); x = bytearray(open(EXE, "rb").read())
    hook_new = b"\xe8" + struct.pack("<i", STUB_VA - (HOOK_VA + 5))
    ho = HOOK_VA - EXE_V2F
    ecur, scur, hcur = bytes(e[CAVE - EP_V2F:CAVE - EP_V2F + len(cave)]), bytes(x[STUB_FO:STUB_FO + 20]), bytes(x[ho:ho + 5])
    nfcur = bytes(e[NF_SITE - EP_V2F:NF_SITE - EP_V2F + 7])
    if nfcur != NF_ORIG and not (nfcur[0] == 0xE9 and CAVE <= NF_SITE + 5 + struct.unpack_from("<i", nfcur, 1)[0] < CAVE_END):
        print("ABORT: NewFrame gate site holds foreign bytes", nfcur.hex()); return 1
    state = ("vanilla" if (not any(ecur), not any(scur), hcur == HOOK_ORIG) == (True, True, True) else
             "ours" if (ecur, scur, hcur, nfcur) == (cave, st, hook_new, nf_new) else "OTHER")
    ro, rtype = reloc_entry(x, RELOC_VA)
    print("AoWEPACK cave %#x (%d B), exe stub %#x, hook %#x: %s | reloc %#x type %s" % (CAVE, len(cave), STUB_VA, HOOK_VA, state, RELOC_VA, rtype))
    if state == "OTHER" and (scur, hcur) == (st, hook_new) and (a.apply or a.revert):
        print("an older build of the rig is installed -> replacing the cave"); state = "old"
    if state == "OTHER": print("ABORT (re-run with --apply to replace an older rig build)"); return 1
    if state == "vanilla":
        if any(e[CAVE - EP_V2F:CAVE_END - EP_V2F]) or any(e[VARS - EP_V2F - 0x400 + 0x400:VARS - EP_V2F]) and False:
            print("ABORT: cave zone not empty"); return 1
        if relocs_in(EP, CAVE, CAVE + len(cave)): print("ABORT: relocs in the cave"); return 1
        if any(x[0x228600 + 0x7C3:0x228600 + 0x800]): print("ABORT: exe stub area not empty"); return 1
    if state == ("vanilla" if a.revert else "ours"):
        print("already %s" % ("reverted" if a.revert else "applied")); return 0
    if not (a.apply or a.revert): print("Dry run OK - rerun with --apply (or --revert)."); return 0
    for p in (EP, EXE):
        b = bak_path(p, BAK)
        if not a.revert and not os.path.exists(b): shutil.copy2(p, b); print("backup ->", b)
    if a.revert:
        ew, xs, xh, rt, nfw = bytes(len(cave)), bytes(20), HOOK_ORIG, 3, NF_ORIG
    else:
        ew, xs, xh, rt, nfw = cave, st, hook_new, 0, nf_new
    with open(EP, "r+b") as f:
        f.seek(CAVE - EP_V2F); f.write(bytes(CAVE_END - CAVE)); f.seek(CAVE - EP_V2F); f.write(ew)
        f.seek(NF_SITE - EP_V2F); f.write(nfw)
    with open(EXE, "r+b") as f:
        f.seek(STUB_FO); f.write(xs)
        f.seek(ho); f.write(xh)
        if ro is not None:
            w = struct.unpack_from("<H", x, ro)[0]
            f.seek(ro); f.write(struct.pack("<H", (w & 0x0FFF) | (rt << 12)))
    print("reverted" if a.revert else "Written")
    return 0


if __name__ == "__main__":
    sys.exit(main())
