#!/usr/bin/env python3
r"""
Title screen 'inioch' intro song v2 (2026-10-23).  AoWx.exe only; UI only (MP-irrelevant).

User: "lets make it so that the title track fades in at 30sec (instead of continuing where it faded out) so that the
drum hits start after the easter egg fade out".

TITLE.IT timing (constant speed 6 / tempo 125 -> 0.12 s per row, 64-row patterns = 7.68 s per order): order 3
(pattern 25) starts at 23.04 s, its last notes are at 28.80 s, order 4 (pattern 26, the drum section) starts at
30.72 s.  Galaxy has no row seek, only an order jump: glxControlMusic(cmd 1, order) [cdecl; sets glxCurrentOrder =
order-1 + glxPatternBreak, the next row advances to `order`, row 0].  So while the music is still muted, at
egg time TJ = T2 - (30.00 - 23.04) = 6.54 s we jump to order 3; it plays on silently and is exactly at 0:30 when
the fade-in starts at T2 = 13.5 s, and the drums come in 0.72 s later.
  Galaxy.glxControlMusic is a SoundP proc-pointer variable 0x5540D050 (filled by GetProcAddress), reached through
  the same SoundP link delta as v1 ([IAT 0x45D958] - 0x554067A8).  Nil pointer / music disabled -> no jump.

In-place upgrade of v1's zone (0x638000..0x638400; magic IEG1 -> IEG2): v1's script can no longer verify itself
because .xtut has grown since, so this one checks the v1 zone byte-for-byte (rebuilt via patch_exe_intro_egg_v1
.build with the stored prev targets) and that the three sites point at v1's labels, then rewrites the zone and
retargets the sites.  New runtime flag D_JMP = 0x638414 (inside v1's reserved data 0x638400..0x638440).
Revert = write v1's blob back + v1 site targets.  Backup .bak_introegg2.

Dry-run default; --apply / --revert / --dis / --exe <copy>.
"""
import argparse, os, shutil, struct, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import patch_exe_intro_egg_v1 as v1

ZONE, ZONE_END, DATA = v1.ZONE, v1.ZONE_END, v1.DATA
MAGIC = b"IEG2"
SUF = ".bak_introegg2"
# 10/23 user: the egg sample skipped at ~7.5 s with glxControlMusic(1, order) - that call also zeroes Galaxy's
# samples-to-next-tick counter [0x1007488C] mid-mix.  Now the jump writes the two song-position bytes directly, the
# way an in-song Bxx does: glxCurrentOrder = order-1, glxPatternBreak = 1 (next tick: order++, row 0).
GLX_ORDER = 0x5540D178                     # SoundP var: &Galaxy.glxCurrentOrder (0x10074D71, GetProcAddress ord 0xE0)
GLX_PBREAK = 0x5540D16C                    # SoundP var: &Galaxy.glxPatternBreak (0x10074868, ord 0xDD)
JUMP_ORDER = 3                             # TITLE.IT order 3 = 23.04 s
T2 = int(round(13.0 / v1.TICK))           # 10/23 user: title track 'moved up' 0.5 s - fade-in 13.0->14.0 (v1: 13.5->14.5; 12.75 tried, reverted)
T3 = int(round(14.0 / v1.TICK))
TJ = T3 - int(round((30.00 - 23.04) / v1.TICK))   # 10/23 user: FULL volume at the track's 0:30 (fade end T3, was fade start T2)
D_JMP = DATA + 0x14
assert v1.T1 < TJ < T2


def build(prev_k, prev_u, prev_d):
    """v1 layout; tick's hold phase additionally fires the one-shot order jump."""
    T1, TEND = v1.T1, v1.TEND
    D_STATE, D_T0, D_V, D_LAST, D_MUS = v1.D_STATE, v1.D_T0, v1.D_V, v1.D_LAST, v1.D_MUS
    IAT_SETMV, IAT_PLAY, QON = v1.IAT_SETMV, v1.IAT_PLAY, v1.QON
    SND_SETMV, SND_GETSFX, SND_GETMUS = v1.SND_SETMV, v1.SND_GETSFX, v1.SND_GETMUS
    WAVNAME = v1.WAVNAME
    lit_hdr = ZONE + 0x20
    lit = struct.pack("<iI", -1, len(WAVNAME)) + WAVNAME + b"\0"
    LIT = lit_hdr + 8
    code_va = ZONE + 0x60
    src = f"""
now:
    push edx
n_again:
    mov edx, dword ptr [0x7ffe000c]
    mov eax, dword ptr [0x7ffe0008]
    cmp edx, dword ptr [0x7ffe0010]
    jne n_again
    shrd eax, edx, 13
    pop edx
    ret

sndbase:
    mov eax, dword ptr [{IAT_SETMV:#x}]
    sub eax, {SND_SETMV:#x}
    ret

setvol:
    mov ecx, dword ptr [{IAT_SETMV:#x}]
    call ecx
    ret

egg_start:
    pushad
    cmp dword ptr [{D_STATE:#x}], 0
    jne es_out
    cmp byte ptr [{QON:#x}], 0
    je es_out
    call sndbase
    mov ebx, eax
    lea eax, [ebx + {SND_GETSFX:#x}]
    call eax
    test al, al
    je es_out
    lea eax, [ebx + {SND_GETMUS:#x}]
    call eax
    mov byte ptr [{D_MUS:#x}], al
    xor esi, esi
    mov eax, dword ptr [0x45a158]
    mov eax, dword ptr [eax]
    test eax, eax
    jz es_nov
    mov eax, dword ptr [eax+0xe8]
    test eax, eax
    jz es_nov
    mov esi, dword ptr [eax+0x148]
    jmp es_clamp
es_nov:
    mov byte ptr [{D_MUS:#x}], 0
es_clamp:
    test esi, esi
    jge es_c1
    xor esi, esi
es_c1:
    cmp esi, 100
    jle es_c2
    mov esi, 100
es_c2:
    mov dword ptr [{D_V:#x}], esi
    mov eax, {LIT:#x}
    mov ecx, dword ptr [{IAT_PLAY:#x}]
    call ecx
    call now
    mov dword ptr [{D_T0:#x}], eax
    mov dword ptr [{D_LAST:#x}], -1
    mov byte ptr [{D_JMP:#x}], 0
    mov dword ptr [{D_STATE:#x}], 1
es_out:
    popad
    jmp {prev_k:#x}

tick:
    cmp dword ptr [{D_STATE:#x}], 0
    je t_ret
    call now
    sub eax, dword ptr [{D_T0:#x}]
    mov ebx, eax
    cmp byte ptr [{D_MUS:#x}], 0
    jne t_mus
    cmp ebx, {TEND}
    jb t_ret
    mov dword ptr [{D_STATE:#x}], 0
    ret
t_mus:
    mov esi, dword ptr [{D_V:#x}]
    cmp ebx, {T1}
    jae t_a
    mov eax, {T1}
    sub eax, ebx
    imul eax, esi
    xor edx, edx
    mov ecx, {T1}
    div ecx
    jmp t_set
t_a:
    cmp ebx, {T2}
    jae t_b
    cmp ebx, {TJ}
    jb t_zero
    cmp byte ptr [{D_JMP:#x}], 0
    jne t_zero
    mov byte ptr [{D_JMP:#x}], 1
    call sndbase
    mov ecx, dword ptr [eax + {GLX_ORDER:#x}]
    mov edx, dword ptr [eax + {GLX_PBREAK:#x}]
    test ecx, ecx
    jz t_zero
    test edx, edx
    jz t_zero
    mov byte ptr [ecx], {JUMP_ORDER - 1}
    mov byte ptr [edx], 1
t_zero:
    xor eax, eax
    jmp t_set
t_b:
    cmp ebx, {T3}
    jae t_done
    mov eax, ebx
    sub eax, {T2}
    imul eax, esi
    xor edx, edx
    mov ecx, {T3 - T2}
    div ecx
    jmp t_set
t_done:
    mov dword ptr [{D_STATE:#x}], 0
    mov eax, esi
    call setvol
    mov dword ptr [{D_LAST:#x}], esi
    ret
t_set:
    cmp eax, dword ptr [{D_LAST:#x}]
    je t_ret
    mov dword ptr [{D_LAST:#x}], eax
    call setvol
t_ret:
    ret

egg_upd:
    pushad
    call tick
    popad
    jmp {prev_u:#x}

egg_des:
    pushad
    cmp dword ptr [{D_STATE:#x}], 0
    je d_out
    mov dword ptr [{D_STATE:#x}], 0
    cmp byte ptr [{D_MUS:#x}], 0
    je d_out
    mov eax, dword ptr [{D_V:#x}]
    call setvol
d_out:
    popad
    jmp {prev_d:#x}
"""
    code = v1.asm(src, code_va)
    labels = {}
    from keystone import Ks, KS_ARCH_X86, KS_MODE_32
    ks = Ks(KS_ARCH_X86, KS_MODE_32)
    for name in ("egg_start", "egg_upd", "egg_des"):
        enc, _ = ks.asm(src + f"\nlookup_{name}:\n    mov eax, {name}\n", code_va)
        labels[name] = struct.unpack_from("<I", bytes(enc), len(bytes(enc)) - 4)[0]
    z = bytearray(ZONE_END - ZONE)
    z[0:4] = MAGIC
    struct.pack_into("<III", z, 0x10, prev_k, prev_u, prev_d)
    z[lit_hdr - ZONE:lit_hdr - ZONE + len(lit)] = lit
    assert code_va + len(code) <= ZONE_END, hex(len(code))
    z[code_va - ZONE:code_va - ZONE + len(code)] = code
    return bytes(z), labels, len(code)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--exe", default=v1.DEFAULT_EXE)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--revert", action="store_true")
    ap.add_argument("--dis", action="store_true")
    a = ap.parse_args()
    d = bytearray(open(a.exe, "rb").read())
    e, secs = v1.sections(d)
    zo = v1.off(secs, ZONE)
    ko, uo, do_ = v1.off(secs, v1.SITE_K), v1.off(secs, v1.SITE_U), v1.off(secs, v1.SITE_D)
    if d[ko] != 0xE9:
        print("ABORT: key site is not a jmp"); return 1
    k_tgt = (v1.SITE_K + 5 + struct.unpack_from("<i", d, ko + 1)[0]) & 0xFFFFFFFF
    u_cur = struct.unpack_from("<I", d, uo)[0]
    d_cur = struct.unpack_from("<I", d, do_)[0]
    magic = bytes(d[zo:zo + 4])
    prev = struct.unpack_from("<III", d, zo + 0x10)
    data_o = v1.off(secs, DATA)
    b1, l1, _ = v1.build(*prev)
    b2, l2, clen = build(*prev)
    cur = bytes(d[zo:zo + len(b1)])
    is_v1 = cur == b1 and (k_tgt, u_cur, d_cur) == (l1["egg_start"], l1["egg_upd"], l1["egg_des"])
    is_v2 = cur == b2 and (k_tgt, u_cur, d_cur) == (l2["egg_start"], l2["egg_upd"], l2["egg_des"])
    print("%s\n  zone magic %s | key -> %#x upd -> %#x des -> %#x | prev %#x/%#x/%#x | v1 %s | v2 %s | "
          "v2 code %d B | jump order %d at %.2f s (fade-in %.2f s)"
          % (a.exe, magic, k_tgt, u_cur, d_cur, *prev, is_v1, is_v2, clen, JUMP_ORDER, TJ * v1.TICK,
             T2 * v1.TICK))
    if a.dis:
        import capstone
        md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
        for i in md.disasm(b2[0x60:0x60 + clen], ZONE + 0x60):
            print("   %08x  %s %s" % (i.address, i.mnemonic, i.op_str))
    if is_v2:
        if not a.revert:
            print("already applied"); return 0
        new, lab = b1, l1
    elif is_v1:
        if a.revert:
            print("not applied - nothing to revert"); return 0
        if any(d[data_o + 0x14:data_o + 0x18]):
            print("ABORT: D_JMP slot not zero in file"); return 1
        rl = v1.relocs(d)
        bad = [hex(r) for r in rl if ZONE - 3 <= r < ZONE_END]
        if bad:
            print("ABORT: relocs in zone: %s" % bad); return 1
        if not a.apply:
            print("Dry run OK - rerun with --apply"); return 0
        new, lab = b2, l2
    else:
        print("ABORT: zone is neither v1 nor v2 (inconsistent)"); return 1
    bp = v1.bak_path(a.exe, SUF)
    if not os.path.exists(bp):
        shutil.copy2(a.exe, bp); print("backup -> " + bp)
    d[zo:zo + len(new)] = new
    struct.pack_into("<i", d, ko + 1, lab["egg_start"] - (v1.SITE_K + 5))
    struct.pack_into("<I", d, uo, lab["egg_upd"])
    struct.pack_into("<I", d, do_, lab["egg_des"])
    with open(a.exe, "r+b") as f:
        f.write(d)
    chk = open(a.exe, "rb").read()
    assert chk[zo:zo + len(new)] == new
    print("Written and verified: %s" % ("v1 restored" if a.revert else
          "title music re-enters at 0:30 (order %d jump at %.2f s)" % (JUMP_ORDER, TJ * v1.TICK)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
