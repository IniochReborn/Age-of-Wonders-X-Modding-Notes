"""
PYROCLASM (227) MAP-WIDE CAST ANIMATION + SHAKE (2026-10-17; user: "pyroclasm gfx: add more particles, and add a shake").
AoWEPACK.dll only.  Separate from patch_pyroclasm_v1.py (terrain) - different sites / zone.

227 is a TAirMastery clone, so its cast plays the Air Mastery map-wide TAnimation whose draw callback is 0x557F050C
(eax = the spell, edx = the animation, [esp+4] = the draw target, ret 8).  The vanilla callback draws Random(3) of the
spell's gfx slots 0..2 at FRAME TIME 0 and only while the SURFACE is viewed ([map+0x88] == 0), then frees the animation at
tick 90 - i.e. a few static ash clouds.  patch_tectonic_shake_v1.py already owns that site (CB: 219 -> its own `tect`,
else the replayed prologue).  This script chains IN FRONT of whatever owns the site at apply time:

  CB  0x557F050C (6 B): jmp -> `cb2` here: [spell+0x10] == 227 -> `pyro`, else jmp to the previous owner (decoded from the
      stored original bytes: the shake script's cb cave, or - if the site was still vanilla - the replayed prologue).

  pyro = 227's own map-wide draw (purely local/visual: own LCG seeded from the animation object, never System.RandSeed or
  the synced RNG; drawn on EVERY level like 219):
    * slot 7 lava-light haze: a few big dim red-orange glows at fixed spots, slowly pulsing;
    * slot 4 embers: N = 50 / 100 / 180 (detail 0 / 1 / 2, [[0x558E945C]+0x6D]) glowing embers rising (96-tick cycles,
      each with its own phase/speed, a +-4 px sway, faded in/out over its cycle - no pop at the wrap);
    * slot 5 ash: N = 30 / 60 / 110 pale ash flakes drifting down-right (128-tick cycles, same envelope idea);
    * slot 6 lava sparks: N = 12 / 24 / 40 from T_ERUPT on: short ballistic arcs (20 of every 56 ticks) thrown up from
      the lower half of the view;
    * T_SHAKE: one shake request (2.4 s, peak 3 px -> the exe cave forces EVEN offsets, map view only - the v3.5 rule);
    * global fade: in over FADE_IN, smoothstep out T_FADE..T_END (every element drawn at level (global + its envelope +
      its 0..15 dither) >> 4, if < K; level = the frame of a K-frame brightness sequence via Show's time argument, as
      Tectonic v3 does) - no retract, nothing pops; T_END: Free (as the vanilla callback does at 90).
  The shake request writes the AoWx.exe shake vars (.xedt 0x62FD00, owned by patch_tectonic_shake_v1.py) with the same
  guards as that script's `req` (PEB ImageBase 0x400000, SizeOfImage >= 0x230000, magic 'TSHK') - if the shake script
  isn't applied the magic is absent and nothing is written.
  The callback only exists after a REAL cast (TGlobalEnchantment.Cast -> TAnimation), never on spell selection.

Gfx slots (pipeline entry 227, see _pyroclasm3fx_integration.txt): 4 ember / 5 ash / 6 spark / 7 haze, each a K-frame
brightness ladder (DualDF 5950..5981).  Slots 0-3 untouched (3 = the terrain glow of patch_pyroclasm_v1.py).
Zone 0x55874400..0x55874C00 (zero, reloc-free; head = MAGIC + the site's original 6 bytes -> exact revert).
LIFO: while applied, patch_tectonic_shake_v1.py sees its CB site as OTHER -> revert this first, run the shake script,
re-apply this.  Dry-run default; --apply / --revert / --dll (scratch copy) / --dis.  Backup AoWEPACK.dll.bak_pyrofx.
"""
import argparse, math, os, shutil, struct, sys
from keystone import Ks, KS_ARCH_X86, KS_MODE_32

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file

BAK_SUFFIX = ".bak_pyrofx"
SPELL_ID = 227
MAGIC = b"PYROFXv1"
BASE = 0x55700000
ZONE, ZONE_END = 0x55874400, 0x55874C00
CB_SITE, CB_VANILLA = 0x557F050C, bytes.fromhex("558bec83c4f0")
DETAIL_CELL, SHOW_THUNK = 0x558E945C, 0x55702904
XV = 0x62FD00
X_MAGIC = b"TSHK"
CAST_REQ = 2400 | (48 << 16)                    # 2.4 s, peak 3.0 px (gentler + longer than Tectonic's 1.8 s / 4.0)
K = 8                                           # brightness levels per particle image
T_END, T_SHAKE, T_ERUPT, T_FADE, FADE_IN = 170, 46, 46, 110, 16
LE, LA, LS, S_LIFE = 96, 128, 56, 20            # cycle lengths: ember / ash / spark (+ spark visible life)
COUNTS = ((50, 100, 180), (30, 60, 110), (12, 24, 40), (4, 6, 10))   # ember / ash / spark / haze per detail 0..2
S_EMB, S_ASH, S_SPK, S_HAZ = 4, 5, 6, 7

ks = Ks(KS_ARCH_X86, KS_MODE_32)


def asm_pic(src, va):
    s1 = src.replace("call $D", ".byte 0xe8, 0, 0, 0, 0")
    for r in ("eax", "ebx", "ecx", "edx", "esi", "edi", "ebp"):
        s1 = s1.replace("sub %s, $D" % r, "sub %s, 0x7fffffff" % r)
    b = bytearray(ks.asm(s1, va)[0])
    k = 0
    while True:
        k = b.find(b"\xe8\x00\x00\x00\x00", k)
        if k < 0: break
        if 0x58 <= b[k + 5] <= 0x5F:
            if b[k + 6] == 0x2D and b[k + 7:k + 11] == b"\xff\xff\xff\x7f":
                struct.pack_into("<I", b, k + 7, va + k + 5)
            elif b[k + 6] == 0x81 and b[k + 8:k + 12] == b"\xff\xff\xff\x7f":
                struct.pack_into("<I", b, k + 8, va + k + 5)
        k += 5
    assert b"\xff\xff\xff\x7f" not in b, "unpatched PIC anchor"
    return bytes(b)


GONE = 16 * K                                   # level x16 at which an element is invisible


def lv_table():
    out = []
    for t in range(T_END):
        if t < FADE_IN: v = GONE * (1 - (t + 1) / (FADE_IN + 1.0))
        elif t >= T_FADE:
            u = (t - T_FADE) / float(T_END - T_FADE); v = GONE * u * u * (3 - 2 * u)
        else: v = 0
        out.append(min(255, int(round(v))))
    return bytes(out)


def env_table(L, rin, rout):
    """per-cycle envelope x16: fade in over rin ticks, out over the last rout ticks (smooth), 0 in between."""
    out = []
    for c in range(L):
        if c < rin: u = 1 - (c + 1) / float(rin + 1)
        elif c >= L - rout: u = (c - (L - rout) + 1) / float(rout)
        else: u = 0.0
        u = u * u * (3 - 2 * u)
        out.append(min(255, int(round(GONE * u))))
    return bytes(out)


def sway_table():
    return bytes((int(round(4 * math.sin(2 * math.pi * k / 64.0))) & 0xFF) for k in range(64))


def build_dll(orig_cb):
    out = bytearray(MAGIC + orig_cb); where = {}
    if orig_cb == CB_VANILLA:
        prev = None
    elif orig_cb[0] == 0xE9 and orig_cb[5] == 0x90:
        prev = CB_SITE + 5 + struct.unpack_from("<i", orig_cb, 1)[0]
    else:
        raise ValueError("callback entry %#x: unexpected bytes %s" % (CB_SITE, orig_cb.hex()))
    C = dict(id=SPELL_ID, xv=XV, xmagic=struct.unpack("<I", X_MAGIC)[0], cast=CAST_REQ, detc=DETAIL_CELL,
             show=SHOW_THUNK, END=T_END, T_SHAKE=T_SHAKE, T_ERUPT=T_ERUPT, K=K, LE=LE, LA=LA, LS=LS, S_LIFE=S_LIFE,
             S_EMB=S_EMB, S_ASH=S_ASH, S_SPK=S_SPK, S_HAZ=S_HAZ, cbret=CB_SITE + 6)
    def place(name, src, pic=False):
        while len(out) % 16: out.append(0)
        va = ZONE + len(out); where[name] = va
        s = src % dict(C, **where)
        s = "\n".join(l for l in s.split("\n") if not l.strip().startswith(";"))   # keystone hangs on comments
        out.extend(asm_pic(s, va) if pic else bytes(ks.asm(s, va)[0]))
    def place_data(name, blob):
        while len(out) % 16: out.append(0)
        where[name] = ZONE + len(out); out.extend(blob)
    place("req", """
        pushad
        mov eax, dword ptr fs:[0x30]
        mov eax, [eax+8]
        cmp eax, 0x400000
        jne r_out
        mov edx, [eax+0x3c]
        cmp dword ptr [eax+edx+0x50], 0x230000
        jb r_out
        cmp dword ptr [%(xv)#x+0xc], %(xmagic)#x
        jne r_out
        mov dword ptr [%(xv)#x], ecx
    r_out:
        popad
        ret
    """)
    place_data("lvt", lv_table())
    place_data("enve", env_table(LE, 10, 28))
    place_data("enva", env_table(LA, 16, 32))
    place_data("envs", env_table(S_LIFE, 2, 10))
    place_data("sway", sway_table())
    place_data("cnt", bytes(c for row in COUNTS for c in row))
    # Frame: -4 seed, -8 t, -0x10 W, -0x14 H, -0x18 i, -0x1c x0, -0x20 y0, -0x24 p, -0x28 v, -0x2c s/u, -0x30 n,
    # -0x3c PIC delta, -0x4c global lev16, -0x50 draw level, -0x58 detail, -0x5c vx
    place("pyro", """
        push ebp
        mov ebp, esp
        sub esp, 0x60
        push ebx
        push esi
        push edi
        mov ebx, edx
        mov edi, eax
        mov esi, dword ptr [ebp+8]
        mov eax, dword ptr [ebx+0x10]
        mov dword ptr [ebp-8], eax
        call $D
        pop ecx
        sub ecx, $D
        mov dword ptr [ebp-0x3c], ecx
        mov eax, dword ptr [ebp-8]
        cmp eax, %(END)d
        jae p_end
        cmp eax, %(T_SHAKE)d
        jne p_ns
        mov ecx, %(cast)#x
        call %(req)#x
    p_ns:
        mov ecx, dword ptr [ebp-0x3c]
        mov eax, dword ptr [ebp-8]
        movzx edx, byte ptr [ecx+eax+%(lvt)#x]
        mov dword ptr [ebp-0x4c], edx
        mov eax, dword ptr [ecx+%(detc)#x]
        mov eax, dword ptr [eax]
        movzx eax, byte ptr [eax+0x6d]
        cmp eax, 2
        jbe p_d
        mov eax, 2
    p_d:
        mov dword ptr [ebp-0x58], eax
        mov eax, dword ptr [ebx+0x34]
        movzx edx, ax
        mov dword ptr [ebp-0x10], edx
        shr eax, 16
        mov dword ptr [ebp-0x14], eax
        mov eax, ebx
        xor eax, 0x6b1d3a57
        mov dword ptr [ebp-4], eax

        ; ---- haze (slot 7): fixed spots, slow pulse
        mov eax, 9
        call p_cnt
        mov dword ptr [ebp-0x18], 0
    h_l:
        mov eax, dword ptr [ebp-0x18]
        cmp eax, dword ptr [ebp-0x30]
        jge h_done
        mov eax, dword ptr [ebp-0x10]
        call p_rnd
        mov dword ptr [ebp-0x1c], eax
        mov eax, dword ptr [ebp-0x14]
        call p_rnd
        mov dword ptr [ebp-0x20], eax
        mov eax, 64
        call p_rnd
        add eax, dword ptr [ebp-8]
        and eax, 63
        sub eax, 32
        cdq
        xor eax, edx
        sub eax, edx
        add eax, eax
        add eax, dword ptr [ebp-0x4c]
        mov ecx, dword ptr [ebp-0x18]
        imul ecx, ecx, 7
        and ecx, 15
        add eax, ecx
        shr eax, 4
        cmp eax, %(K)d
        jae h_n
        mov dword ptr [ebp-0x50], eax
        mov edx, %(S_HAZ)d
        mov ecx, dword ptr [ebp-0x1c]
        mov eax, dword ptr [ebp-0x20]
        call p_drw
    h_n:
        inc dword ptr [ebp-0x18]
        jmp h_l
    h_done:

        ; ---- embers (slot 4): rise, sway, per-cycle envelope
        xor eax, eax
        call p_cnt
        mov dword ptr [ebp-0x18], 0
    e_l:
        mov eax, dword ptr [ebp-0x18]
        cmp eax, dword ptr [ebp-0x30]
        jge e_done
        mov eax, dword ptr [ebp-0x10]
        add eax, 160
        call p_rnd
        sub eax, 80
        mov dword ptr [ebp-0x1c], eax
        mov eax, dword ptr [ebp-0x14]
        add eax, 80
        call p_rnd
        add eax, 20
        mov dword ptr [ebp-0x20], eax
        mov eax, %(LE)d
        call p_rnd
        mov dword ptr [ebp-0x24], eax
        mov eax, 8
        call p_rnd
        add eax, 4
        mov dword ptr [ebp-0x28], eax
        mov eax, 64
        call p_rnd
        mov dword ptr [ebp-0x2c], eax
        mov eax, dword ptr [ebp-8]
        add eax, dword ptr [ebp-0x24]
        xor edx, edx
        mov ecx, %(LE)d
        div ecx
        mov ecx, dword ptr [ebp-0x3c]
        movzx eax, byte ptr [ecx+edx+%(enve)#x]
        push edx
        add eax, dword ptr [ebp-0x4c]
        mov edx, dword ptr [ebp-0x18]
        imul edx, edx, 11
        and edx, 15
        add eax, edx
        shr eax, 4
        pop edx
        cmp eax, %(K)d
        jae e_n
        mov dword ptr [ebp-0x50], eax
        imul edx, dword ptr [ebp-0x28]
        sar edx, 3
        mov eax, dword ptr [ebp-0x20]
        sub eax, edx
        push eax
        mov edx, dword ptr [ebp-8]
        add edx, dword ptr [ebp-0x2c]
        and edx, 63
        movsx ecx, byte ptr [ecx+edx+%(sway)#x]
        add ecx, dword ptr [ebp-0x1c]
        pop eax
        mov edx, %(S_EMB)d
        call p_drw
    e_n:
        inc dword ptr [ebp-0x18]
        jmp e_l
    e_done:

        ; ---- ash (slot 5): drift down-right
        mov eax, 3
        call p_cnt
        mov dword ptr [ebp-0x18], 0
    a_l:
        mov eax, dword ptr [ebp-0x18]
        cmp eax, dword ptr [ebp-0x30]
        jge a_done
        mov eax, dword ptr [ebp-0x10]
        add eax, 200
        call p_rnd
        sub eax, 150
        mov dword ptr [ebp-0x1c], eax
        mov eax, dword ptr [ebp-0x14]
        add eax, 100
        call p_rnd
        sub eax, 100
        mov dword ptr [ebp-0x20], eax
        mov eax, %(LA)d
        call p_rnd
        mov dword ptr [ebp-0x24], eax
        mov eax, 6
        call p_rnd
        add eax, 3
        mov dword ptr [ebp-0x2c], eax
        mov eax, 5
        call p_rnd
        add eax, 2
        mov dword ptr [ebp-0x28], eax
        mov eax, 64
        call p_rnd
        mov dword ptr [ebp-0x5c], eax
        mov eax, dword ptr [ebp-8]
        add eax, dword ptr [ebp-0x24]
        xor edx, edx
        mov ecx, %(LA)d
        div ecx
        mov ecx, dword ptr [ebp-0x3c]
        movzx eax, byte ptr [ecx+edx+%(enva)#x]
        push edx
        add eax, dword ptr [ebp-0x4c]
        mov edx, dword ptr [ebp-0x18]
        imul edx, edx, 13
        and edx, 15
        add eax, edx
        shr eax, 4
        pop edx
        cmp eax, %(K)d
        jae a_n
        mov dword ptr [ebp-0x50], eax
        mov eax, edx
        imul eax, dword ptr [ebp-0x28]
        sar eax, 4
        add eax, dword ptr [ebp-0x20]
        push eax
        imul edx, dword ptr [ebp-0x2c]
        sar edx, 4
        add edx, dword ptr [ebp-0x1c]
        push edx
        mov edx, dword ptr [ebp-8]
        add edx, dword ptr [ebp-0x5c]
        and edx, 63
        movsx eax, byte ptr [ecx+edx+%(sway)#x]
        sar eax, 1
        pop ecx
        add ecx, eax
        pop eax
        mov edx, %(S_ASH)d
        call p_drw
    a_n:
        inc dword ptr [ebp-0x18]
        jmp a_l
    a_done:

        ; ---- lava sparks (slot 6): from T_ERUPT, 20 of every LS ticks, ballistic
        mov eax, 6
        call p_cnt
        mov dword ptr [ebp-0x18], 0
    s_l:
        mov eax, dword ptr [ebp-0x18]
        cmp eax, dword ptr [ebp-0x30]
        jge s_done
        mov eax, dword ptr [ebp-0x10]
        call p_rnd
        mov dword ptr [ebp-0x1c], eax
        mov eax, dword ptr [ebp-0x14]
        shr eax, 1
        inc eax
        call p_rnd
        mov edx, dword ptr [ebp-0x14]
        shr edx, 1
        add eax, edx
        mov dword ptr [ebp-0x20], eax
        mov eax, %(LS)d
        call p_rnd
        mov dword ptr [ebp-0x24], eax
        mov eax, 9
        call p_rnd
        sub eax, 4
        mov dword ptr [ebp-0x5c], eax
        mov eax, 4
        call p_rnd
        add eax, 4
        mov dword ptr [ebp-0x28], eax
        mov eax, dword ptr [ebp-8]
        sub eax, %(T_ERUPT)d
        jl s_n
        add eax, dword ptr [ebp-0x24]
        xor edx, edx
        mov ecx, %(LS)d
        div ecx
        cmp edx, %(S_LIFE)d
        jae s_n
        mov ecx, dword ptr [ebp-0x3c]
        movzx eax, byte ptr [ecx+edx+%(envs)#x]
        push edx
        add eax, dword ptr [ebp-0x4c]
        mov edx, dword ptr [ebp-0x18]
        imul edx, edx, 5
        and edx, 15
        add eax, edx
        shr eax, 4
        pop edx
        cmp eax, %(K)d
        jae s_n
        mov dword ptr [ebp-0x50], eax
        mov eax, edx
        imul eax, edx
        sar eax, 2
        mov ecx, edx
        imul ecx, dword ptr [ebp-0x28]
        sub eax, ecx
        add eax, dword ptr [ebp-0x20]
        mov ecx, edx
        imul ecx, dword ptr [ebp-0x5c]
        sar ecx, 1
        add ecx, dword ptr [ebp-0x1c]
        mov edx, %(S_SPK)d
        call p_drw
    s_n:
        inc dword ptr [ebp-0x18]
        jmp s_l
    s_done:

    p_end:
        cmp dword ptr [ebx+0x10], %(END)d
        jl p_ret
        mov dl, 1
        mov eax, ebx
        mov ecx, dword ptr [eax]
        call dword ptr [ecx-4]
    p_ret:
        pop edi
        pop esi
        pop ebx
        mov esp, ebp
        pop ebp
        ret 8
    p_cnt:
        add eax, dword ptr [ebp-0x58]
        mov ecx, dword ptr [ebp-0x3c]
        movzx eax, byte ptr [ecx+eax+%(cnt)#x]
        mov dword ptr [ebp-0x30], eax
        ret
    p_rnd:
        push ecx
        push edx
        mov ecx, eax
        mov eax, dword ptr [ebp-4]
        imul eax, eax, 0x08088405
        inc eax
        mov dword ptr [ebp-4], eax
        mul ecx
        mov eax, edx
        pop edx
        pop ecx
        ret
    p_drw:
        add ecx, dword ptr [esi+0x10]
        add eax, dword ptr [esi+0x14]
        push eax
        push dword ptr [ebp-0x50]
        push esi
        mov eax, dword ptr [edi+0x2c]
        call %(show)#x
        ret
    """, pic=True)
    if prev is None:
        place("cb2", """
            cmp dword ptr [eax+0x10], %(id)d
            je %(pyro)#x
            push ebp
            mov ebp, esp
            add esp, -0x10
            jmp %(cbret)#x
        """)
    else:
        C["prev"] = prev
        place("cb2", """
            cmp dword ptr [eax+0x10], %(id)d
            je %(pyro)#x
            jmp %(prev)#x
        """)
    return bytes(out), where


def relocs(d, base):
    import pefile
    pe = pefile.PE(data=bytes(d), fast_load=True); pe.parse_data_directories(directories=[pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_BASERELOC"]])
    return [base + e.rva for b in getattr(pe, "DIRECTORY_ENTRY_BASERELOC", []) for e in b.entries if e.type]


def foff(d, base, va):
    import pefile
    pe = pefile.PE(data=bytes(d), fast_load=True)
    return pe.get_offset_from_rva(va - base)


def jmp_to(site, tgt):
    return b"\xe9" + struct.pack("<i", tgt - site - 5)


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--apply", action="store_true"); ap.add_argument("--revert", action="store_true")
    ap.add_argument("--dis", action="store_true"); ap.add_argument("--dll", default=None)
    a = ap.parse_args()
    dll = a.dll or game_file("AoWEPACK.dll")
    d = bytearray(open(dll, "rb").read())
    print("target:", dll)
    rl = relocs(d, BASE)
    bad = [hex(r) for r in rl if ZONE <= r < ZONE_END or CB_SITE - 3 < r < CB_SITE + 6]
    if bad: print("ABORT: relocs in zone / site %s" % bad); return 1
    zo = foff(d, BASE, ZONE); zl = bytes(d[zo:zo + ZONE_END - ZONE]); co = foff(d, BASE, CB_SITE)
    live_cb = bytes(d[co:co + 6])
    if zl[:8] == MAGIC: stored = True; orig_cb = zl[8:14]
    elif any(zl): print("ABORT: zone %#x..%#x is not free" % (ZONE, ZONE_END)); return 1
    else: stored = False; orig_cb = live_cb
    try: code, where = build_dll(orig_cb)
    except ValueError as ex: print("ABORT:", ex); return 1
    assert ZONE + len(code) <= ZONE_END, "zone overflow"
    want_cb = jmp_to(CB_SITE, where["cb2"]) + b"\x90"
    if not stored: s_cb = "free (prev %s)" % ("vanilla" if orig_cb == CB_VANILLA else "chain -> %#x" % (CB_SITE + 5 + struct.unpack_from("<i", orig_cb, 1)[0]))
    elif live_cb == want_cb: s_cb = "ours"
    elif live_cb[0] == 0xE9 and ZONE <= CB_SITE + 5 + struct.unpack_from("<i", live_cb, 1)[0] < ZONE_END: s_cb = "ours(old)"
    else: s_cb = "OTHER"
    print("zone %s (%d B) | CB site %s | caves %s" % ("ours" if stored else "zero", len(code), s_cb,
          ", ".join("%s=%#x" % kv for kv in where.items())))
    if a.dis:
        import capstone
        md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
        for nm in ("pyro", "cb2"):
            for i in md.disasm(code[where[nm] - ZONE:], where[nm]): print("   %08X  %-20s %s %s" % (i.address, i.bytes.hex(), i.mnemonic, i.op_str))
    if a.revert:
        if not stored: print("already vanilla"); return 0
        if s_cb == "OTHER": print("ABORT: the CB site no longer points at us (revert that patch first)"); return 1
        d[co:co + 6] = orig_cb; d[zo:zo + ZONE_END - ZONE] = bytes(ZONE_END - ZONE)
        with open(dll, "r+b") as f: f.write(bytes(d))
        print("reverted (CB site -> %s)" % orig_cb.hex()); return 0
    if stored and s_cb == "OTHER": print("ABORT: the CB site was taken over by someone else (%s)" % live_cb.hex()); return 1
    nd = bytearray(d); nd[zo:zo + ZONE_END - ZONE] = code + bytes(ZONE_END - ZONE - len(code)); nd[co:co + 6] = want_cb
    if nd == d: print("already applied"); return 0
    print("%d bytes change" % sum(1 for x, y in zip(d, nd) if x != y))
    if not a.apply: print("Dry run OK - rerun with --apply (or --revert)."); return 0
    if a.dll is None:
        bak = bak_path(dll, BAK_SUFFIX)
        if not os.path.exists(bak): shutil.copy2(dll, bak); print("backup ->", bak)
    with open(dll, "r+b") as f: f.write(bytes(nd))
    assert open(dll, "rb").read() == bytes(nd)
    print("written and verified"); return 0


if __name__ == "__main__":
    sys.exit(main())
