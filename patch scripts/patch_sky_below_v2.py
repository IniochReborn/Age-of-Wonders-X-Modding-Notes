#!/usr/bin/env python3
r"""
AoWEPACK sky overlay: Sky / Clear Sky shows the level BELOW on every level, nested (2026-11-13).

User: "sky and clear sky have, on the firmament, show the surface below (cool transparency effect). however, sky on
the surface doesnt show levels below it. i want to add this feature. also, if there are two sky terrains over each
other, such as on both firmament and surface, i want to be able to see the level below surface from the firmament".

Before: the overlay (sky_clouds_overlay_asm, water build) blended Ziggurat's cached Surface render into Sky pixels
only while the viewport showed level 3; the cache builder (relocated Ziggurat code 0x558C0900) hard-codes level 0.
Now (layered byte patch over the installed water build):
  * builder takes its level from BLVL (2 sites -> stubs) and, after each full-resolution 608x608 chunk is drawn
    and before it is scaled into the cache, calls the overlay core on the chunk while COMPOSE is set -> that level's
    own Sky pixels get the next lower level's cache (INNER buffer) blended in (same per-kind weights, clouds frozen).
  * overlay 'fmtok' block -> call SETUP: viewed level V, B = next VISIBLE level below in display order (engine
    thunk 0x55851210, honours the hidden-level mask); nothing happens unless a Sky hex is in view; then the chain
    B, below(B), ... (continues only while the level has Sky hexes, max 4) is rendered deepest-first, each one
    composited into the next; cache key = map + pixel format, invalidated whenever the viewed level changes
    and whenever the overlay
    was not drawn for 2 s (game load, combat, full-screen window) - so leaving and coming back refreshes it.
State: AoWEPACK DATA slack 0x558E9AA0..0x558E9AC4 (zero, unclaimed).  Cave 0x558E1900..0x558E1E00 'SKB1'.
⚠ Revert this before re-running patch_sky_overlay_water_v1 / sky polish (they would see OTHER).
Dry-run default; --apply; --revert; --test (unicorn test of SETUP / chain logic).  Backup .bak_skybelow.

v2 (2026-11-13, user: "when i use the editor screenshot, the new sky terrains including chasm look bad"): the
screenshot DLL (build_aowxshot.py) draws the map offscreen with the objects' Show calls, so it never got the overlay
(clouds, stars, Chasm webs, sky fog, level-below see-through).  v2 adds an entry table for it at CAVE+0x10
(5-byte jumps: +0x10 shot_begin(eax map, edx desc) / +0x15 shot_pass(eax, edx, ecx mode 0 static | 2 after the
dynamic list) / +0x1A shot_end), header magic 'SKB2' (the DLL checks it).  While SHOT is set: time is frozen at
SHOT_T (overlay timing call -> gettime2; the chunks of one image must share one cloud field), the level-below image
is anchored at world 0 instead of following the scroll (chunks have different scrolls), the Sky-in-view scan covers
the whole level and the 2 s idle rule is off.  shot_end invalidates the cache.  Upgrades an installed v1 in place.
"""
import os, shutil, struct, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from bakpath import bak_path, game_file  # noqa: E402
import patch_sky_polish_v1 as SP  # noqa: E402
import sky_clouds_overlay_asm as OV  # noqa: E402
import patch_sky_below_v1 as V1  # noqa: E402

EPK = game_file("AoWEPACK.dll")
B = 0x55700C00
TAG = ".bak_skybelow"
CAVE, CAVE_END, MAGIC = 0x558E1900, 0x558E1E00, b"SKB2"
ST = 0x558E9AA0
BLVL, COMPOSE, IN_BUF, IN_W, IN_H, LASTV, LASTT = ST, ST + 4, ST + 8, ST + 0xC, ST + 0x10, ST + 0x14, ST + 0x18
SHOT, SHOT_T = ST + 0x1C, ST + 0x20
ENTRIES = CAVE + 0x10          # shot_begin / shot_pass / shot_end (5-byte jumps)
CODE = CAVE + 0x20
GAP_MS = 2000                 # overlay not called for this long (load, combat, full-screen window) -> rebuild
BELOW = 0x55851210            # NeighbourLevel(eax level, dl=1 down) -> eax level / -1, hidden levels skipped
FREEMEM = 0x558FB714          # import slot (eax = ptr)
BSS_CAP = 0x558FAF18
MAXCHAIN = 4
# builder sites (relocated Ziggurat block)
SITE_A = (0x558C093E, bytes.fromhex("ba00000000"))                    # mov edx, 0
SITE_B = (0x558C0B06, bytes.fromhex("c7838800000000000000"))          # mov dword [ebx+0x88], 0
SITE_C = (0x558C0CC6, bytes.fromhex("8b44241c6bc060"))                # mov eax,[esp+0x1c] / imul eax,eax,0x60


def cave_src(core):
    L = OV.L
    f = {k: "dword ptr [edi + %#x]" % o for k, o in L.items()}
    g = lambda a: "dword ptr [ebp + %#x]" % a  # noqa: E731
    return f"""
    setup:
        mov {f['SURF']}, 0
        cmp {f['MODE']}, 0
        jne s_ret
        push ebx
        push esi
        mov esi, eax
        cmp {g(COMPOSE)}, 0
        je s_norm
        mov eax, {g(IN_BUF)}
        test eax, eax
        je s_out
        mov ebx, {g(IN_W)}
        test ebx, ebx
        jle s_out
        mov {f['SW']}, ebx
        mov ebx, {g(IN_H)}
        test ebx, ebx
        jle s_out
        mov {f['SH']}, ebx
        mov {f['PX']}, 0
        mov {f['PY']}, 0
        mov {f['SURF']}, eax
        jmp s_out
    s_norm:
        mov eax, dword ptr [esi + 0x88]
        cmp eax, {g(LASTV)}
        je s_same
        mov {g(LASTV)}, eax
        mov {g(OV.BSS_OK)}, 0
    s_same:
        cmp {g(SHOT)}, 0
        jne s_t1
        push ecx
        push edx
        call gettime
        pop edx
        pop ecx
        mov ebx, eax
        sub eax, {g(LASTT)}
        mov {g(LASTT)}, ebx
        cmp eax, {GAP_MS}
        jbe s_t1
        mov {g(OV.BSS_OK)}, 0
    s_t1:
        mov eax, dword ptr [esi + 0x88]
        push edx
        mov dl, 1
        call {BELOW:#x}
        pop edx
        test eax, eax
        js s_out
        mov ebx, eax
        cmp {g(OV.BSS_OK)}, 0
        je s_need
        cmp {g(OV.BSS_MAP)}, esi
        jne s_need
        cmp {g(OV.BSS_FMT)}, ecx
        je s_use
    s_need:
        push edx
        push ebx
        mov edx, dword ptr [esi + 0x88]
        mov eax, dword ptr [esi + 0x10]
        call {OV.GETLEVEL:#x}
        test eax, eax
        je s_nv
        mov ebx, eax
        mov ecx, dword ptr [esi + 0x94]
        mov {f['X']}, ecx
        add ecx, dword ptr [esi + 0x9c]
        mov {f['XEND']}, ecx
        mov ecx, dword ptr [esi + 0x98]
        mov {f['WX']}, ecx
        add ecx, dword ptr [esi + 0xa0]
        mov {f['YEND']}, ecx
        cmp {g(SHOT)}, 0
        je s_scan
        mov {f['X']}, 0
        mov {f['WX']}, 0
        mov {f['XEND']}, 0x7fffffff
        mov {f['YEND']}, 0x7fffffff
    s_scan:
        call scan
    s_nv:
        pop ebx
        pop edx
        test eax, eax
        je s_out
        call chain
        call gettime
        mov {g(LASTT)}, eax
    s_use:
        mov ecx, {g(OV.BSS_BUF)}
        test ecx, ecx
        je s_out
        mov eax, {g(OV.BSS_W)}
        test eax, eax
        jle s_out
        mov {f['SW']}, eax
        mov eax, {g(OV.BSS_H)}
        test eax, eax
        jle s_out
        mov {f['SH']}, eax
        mov {f['SURF']}, ecx
        mov ecx, dword ptr [esi + 0x80]
        mov eax, ecx
        sar eax, 2
        sub ecx, eax
        mov {f['PX']}, ecx
        mov ecx, dword ptr [esi + 0x84]
        mov eax, ecx
        sar eax, 2
        sub ecx, eax
        mov {f['PY']}, ecx
        cmp {g(SHOT)}, 0
        je s_out
        mov {f['PX']}, 0
        mov {f['PY']}, 0
    s_out:
        pop esi
        pop ebx
    s_ret:
        ret

    scan:
        cmp {f['X']}, 0
        jge sc1
        mov {f['X']}, 0
    sc1:
        cmp {f['WX']}, 0
        jge sc2
        mov {f['WX']}, 0
    sc2:
        mov eax, dword ptr [ebx + 0xc]
        cmp {f['XEND']}, eax
        jle sc3
        mov {f['XEND']}, eax
    sc3:
        mov eax, dword ptr [ebx + 0x10]
        cmp {f['YEND']}, eax
        jle sc_x
        mov {f['YEND']}, eax
    sc_x:
        mov ecx, {f['X']}
        cmp ecx, {f['XEND']}
        jge sc_none
        mov edx, {f['WX']}
    sc_y:
        cmp edx, {f['YEND']}
        jge sc_xn
        mov eax, dword ptr [ebx + 0x74]
        mov eax, dword ptr [eax + ecx*4]
        push esi
        mov esi, dword ptr [ebx + 0x78]
        add eax, dword ptr [esi + edx*4]
        pop esi
        cmp byte ptr [eax + 0x14], 0xe
        je sc_found
        inc edx
        jmp sc_y
    sc_xn:
        inc {f['X']}
        jmp sc_x
    sc_found:
        mov eax, 1
        ret
    sc_none:
        xor eax, eax
        ret

    chain:
        pushal
        sub esp, 0x20
        mov dword ptr [esp + 0x14], edx
        mov dword ptr [esp], ebx
        mov dword ptr [esp + 0x10], 1
    ch_l:
        mov ecx, dword ptr [esp + 0x10]
        cmp ecx, {MAXCHAIN}
        jge ch_go
        mov edx, dword ptr [esp + ecx*4 - 4]
        mov eax, dword ptr [esi + 0x10]
        call {OV.GETLEVEL:#x}
        test eax, eax
        je ch_go
        mov ebx, eax
        mov {f['X']}, 0
        mov {f['WX']}, 0
        mov {f['XEND']}, 0x7fffffff
        mov {f['YEND']}, 0x7fffffff
        call scan
        test eax, eax
        je ch_go
        mov ecx, dword ptr [esp + 0x10]
        mov eax, dword ptr [esp + ecx*4 - 4]
        mov dl, 1
        call {BELOW:#x}
        test eax, eax
        js ch_go
        mov dword ptr [esp + ecx*4], eax
        inc dword ptr [esp + 0x10]
        jmp ch_l
    ch_go:
        call freein
    ch_b:
        dec dword ptr [esp + 0x10]
        mov ecx, dword ptr [esp + 0x10]
        mov eax, dword ptr [esp + ecx*4]
        mov {g(BLVL)}, eax
        mov {g(COMPOSE)}, 1
        mov eax, esi
        mov edx, dword ptr [esp + 0x14]
        call {OV.ZIG_CACHE:#x}
        mov {g(COMPOSE)}, 0
        call freein
        cmp dword ptr [esp + 0x10], 0
        je ch_done
        mov eax, {g(OV.BSS_BUF)}
        mov {g(IN_BUF)}, eax
        mov eax, {g(OV.BSS_W)}
        mov {g(IN_W)}, eax
        mov eax, {g(OV.BSS_H)}
        mov {g(IN_H)}, eax
        mov {g(OV.BSS_BUF)}, 0
        mov {g(BSS_CAP)}, 0
        jmp ch_b
    ch_done:
        add esp, 0x20
        popal
        ret

    gettime:
        mov eax, dword ptr [ebp + {OV.IAT_HSE_GETMAPLEVEL:#x}]
        sub eax, {OV.HSE_GETMAPLEVEL:#x}
        call dword ptr [eax + {OV.HSE_IAT_TIMEGETTIME:#x}]
        ret

    gettime2:
        cmp {g(SHOT)}, 0
        je gt2_live
        mov eax, {g(SHOT_T)}
        ret
    gt2_live:
        call dword ptr [eax + {OV.HSE_IAT_TIMEGETTIME:#x}]
        ret

    shot_begin:
        pushal
        call sb_b
    sb_b:
        pop ebp
        sub ebp, sb_b
        push eax
        push edx
        call gettime
        mov {g(SHOT_T)}, eax
        mov {g(SHOT)}, 1
        mov {g(OV.BSS_OK)}, 0
        pop edx
        pop eax
        push 0
        call {core:#x}
        popal
        ret
    shot_pass:
        push ecx
        call {core:#x}
        ret
    shot_end:
        pushal
        call se_b
    se_b:
        pop ebp
        sub ebp, se_b
        mov {g(SHOT)}, 0
        mov {g(OV.BSS_OK)}, 0
        mov {g(LASTV)}, -1
        popal
        ret

    freein:
        mov eax, {g(IN_BUF)}
        test eax, eax
        je fi_x
        mov {g(IN_BUF)}, 0
        call dword ptr [ebp + {FREEMEM:#x}]
    fi_x:
        ret

    stub_a:
        mov edx, {g(BLVL)}
        ret
    stub_b:
        mov eax, {g(BLVL)}
        mov dword ptr [ebx + 0x88], eax
        ret
    stub_c:
        cmp {g(COMPOSE)}, 0
        je sc_skip
        cmp {g(IN_BUF)}, 0
        je sc_skip
        mov eax, dword ptr [esp + 4]
        lea edx, [esp + 0x54]
        push 0
        call {core:#x}
    sc_skip:
        mov eax, dword ptr [esp + 0x20]
        imul eax, eax, 0x60
        ret
    .long setup
    .long stub_a
    .long stub_b
    .long stub_c
    .long gettime2
    .long shot_begin
    .long shot_pass
    .long shot_end
"""


def rel(op, at, to):
    return bytes([op]) + struct.pack("<i", to - (at + 5))


def build():
    """-> list of (va, old, new)"""
    core = OV.core_va(True)
    code = OV.asm(cave_src(core), CODE)
    setup, sa, sb, sc, gt2, s_beg, s_pass, s_end = struct.unpack("<8I", code[-32:])
    code = code[:-32]
    tbl = b"".join(rel(0xE9, ENTRIES + 5 * i, t) for i, t in enumerate((s_beg, s_pass, s_end)))
    cave = MAGIC + bytes(12) + tbl + bytes([0x90]) + code
    assert len(cave) <= CAVE_END - CAVE, hex(len(cave))
    full = OV.asm(OV.src(True) + "    .long fmtok\n    .long timing\n", OV.ZONE + 0x10)
    fmtok, timing = struct.unpack("<2I", full[-8:])
    tg = timing + 11                                     # after mov eax,[ebp+IAT] / sub eax, imm32
    tg_old = bytes([0x8B, 0x80]) + struct.pack("<I", OV.HSE_IAT_TIMEGETTIME) + bytes([0xFF, 0xD0])
    assert full[tg - OV.ZONE - 0x10:tg - OV.ZONE - 0x10 + 8] == tg_old
    old = full[fmtok - OV.ZONE - 0x10:timing - OV.ZONE - 0x10]
    new = rel(0xE8, fmtok, setup) + rel(0xE9, fmtok + 5, timing)
    new += b"\x90" * (len(old) - len(new))
    P = [(CAVE, bytes(len(cave)), cave), (fmtok, old, new), (tg, tg_old, rel(0xE8, tg, gt2) + bytes([0x90] * 3))]
    for (va, o), stub in zip((SITE_A, SITE_B, SITE_C), (sa, sb, sc)):
        n = rel(0xE8, va, stub)
        P.append((va, o, n + b"\x90" * (len(o) - len(n))))
    return P, dict(setup=setup, sa=sa, sb=sb, sc=sc, cave=cave)


def test():
    from unicorn import Uc, UC_ARCH_X86, UC_MODE_32, UC_HOOK_CODE
    from unicorn.x86_const import (UC_X86_REG_EAX, UC_X86_REG_EBX, UC_X86_REG_ECX, UC_X86_REG_EDX, UC_X86_REG_ESI,
                                   UC_X86_REG_EDI, UC_X86_REG_EBP, UC_X86_REG_ESP, UC_X86_REG_EIP)
    P, e = build()
    L = OV.L
    fails = 0

    def run(levels, view, hidden=(), ok=0, lastv=None, compose=None, vis=(0, 0, 4, 4), fmt=0x56509310,
            gap=16, shot=0):
        """levels: {idx: set of (x,y) sky hexes} on 4x4 maps.  -> (frame dict, calls list, state)"""
        mu = Uc(UC_ARCH_X86, UC_MODE_32)
        mu.mem_map(0x55700000, 0x300000)           # code + DATA + BSS
        mu.mem_map(0x100000, 0x100000)             # stack / frame
        mu.mem_map(0x300000, 0x100000)             # fake objects
        mu.mem_map(0x55600000, 0x100000)           # HSEPack import slot
        mu.mem_write(CAVE, e["cave"])
        MAP, DC, LVL0, RET = 0x300000, 0x300400, 0x310000, 0x55900000
        w = lambda a, v: mu.mem_write(a, struct.pack("<I", v & 0xFFFFFFFF))  # noqa: E731
        r = lambda a: struct.unpack("<I", bytes(mu.mem_read(a, 4)))[0]       # noqa: E731
        w(MAP + 0x10, 0x300800); w(MAP + 0x88, view); w(MAP + 0x80, 400); w(MAP + 0x84, -40)
        for k, v in zip((0x94, 0x98, 0x9c, 0xa0), vis):
            w(MAP + k, v)
        for idx, sky in levels.items():
            base = LVL0 + idx * 0x1000
            w(base + 0xc, 4); w(base + 0x10, 4); w(base + 0x74, base + 0x100); w(base + 0x78, base + 0x200)
            for i in range(4):
                w(base + 0x100 + i * 4, base + 0x400 + i * 0x100); w(base + 0x200 + i * 4, i * 0x20)
            for x in range(4):
                for y in range(4):
                    mu.mem_write(base + 0x400 + x * 0x100 + y * 0x20 + 0x14, bytes([0xE if (x, y) in sky else 2]))
        w(OV.BSS_OK, ok); w(OV.BSS_MAP, MAP if ok else 0); w(OV.BSS_FMT, fmt if ok else 0)
        if ok:
            w(OV.BSS_BUF, 0xAAAA0000); w(OV.BSS_W, 192); w(OV.BSS_H, 96); w(BSS_CAP, 1)
        w(LASTV, view if lastv is None else lastv)
        if compose:
            w(COMPOSE, 1); w(IN_BUF, compose[0]); w(IN_W, compose[1]); w(IN_H, compose[2])
        FRAME, SP0 = 0x180000, 0x170000
        w(FRAME + L['MODE'], 0)
        w(SP0, RET)
        w(FREEMEM, 0x55900010)
        w(OV.IAT_HSE_GETMAPLEVEL, OV.HSE_GETMAPLEVEL); w(OV.HSE_IAT_TIMEGETTIME, 0x55900020)
        T0 = 0xFFFFFF00                             # wraps during the test
        w(LASTT, T0 - gap); tcalls = [0]; w(SHOT, shot)
        calls, nbuf = [], [0]
        order = [3, 0, 1, 2] + list(range(4, 29))

        def ret(val=None):
            sp = mu.reg_read(UC_X86_REG_ESP)
            if val is not None:
                mu.reg_write(UC_X86_REG_EAX, val & 0xFFFFFFFF)
            mu.reg_write(UC_X86_REG_EIP, r(sp)); mu.reg_write(UC_X86_REG_ESP, sp + 4)

        def hook(uc, addr, size, _):
            if addr == BELOW:
                lv = uc.reg_read(UC_X86_REG_EAX); p = order.index(lv) + 1; res = -1
                while p < len(order):
                    if order[p] in levels and order[p] not in hidden:
                        res = order[p]; break
                    p += 1
                ret(res)
            elif addr == OV.GETLEVEL:
                lv = uc.reg_read(UC_X86_REG_EDX)
                uc.reg_write(UC_X86_REG_ECX, 0xDEAD); uc.reg_write(UC_X86_REG_EDX, 0xBEEF)
                ret(LVL0 + lv * 0x1000 if lv in levels else 0)
            elif addr == OV.ZIG_CACHE:
                assert uc.reg_read(UC_X86_REG_EAX) == MAP and uc.reg_read(UC_X86_REG_EDX) == DC
                assert r(COMPOSE) == 1
                calls.append(("build", r(BLVL), r(IN_BUF)))
                if r(BSS_CAP) == 0:
                    nbuf[0] += 1; w(OV.BSS_BUF, 0xB0000000 + nbuf[0]); w(BSS_CAP, 1)
                w(OV.BSS_W, 192 + nbuf[0]); w(OV.BSS_H, 96); w(OV.BSS_OK, 1); w(OV.BSS_MAP, MAP); w(OV.BSS_FMT, fmt)
                ret()
            elif addr == 0x55900020:
                tcalls[0] += 1
                uc.reg_write(UC_X86_REG_ECX, 0x3333); uc.reg_write(UC_X86_REG_EDX, 0x4444)
                ret(T0 + (tcalls[0] - 1) * 700)
            elif addr == 0x55900010:
                calls.append(("free", uc.reg_read(UC_X86_REG_EAX)))
                uc.reg_write(UC_X86_REG_ECX, 0x1111); uc.reg_write(UC_X86_REG_EDX, 0x2222)
                ret()
        mu.hook_add(UC_HOOK_CODE, hook)
        for reg, v in ((UC_X86_REG_EAX, MAP), (UC_X86_REG_EDX, DC), (UC_X86_REG_ECX, fmt), (UC_X86_REG_EDI, FRAME),
                       (UC_X86_REG_EBP, 0), (UC_X86_REG_ESP, SP0), (UC_X86_REG_EBX, 0x1234), (UC_X86_REG_ESI, 0x5678)):
            mu.reg_write(reg, v)
        mu.emu_start(e["setup"], RET, count=200000)
        assert mu.reg_read(UC_X86_REG_EIP) == RET and mu.reg_read(UC_X86_REG_ESP) == SP0 + 4
        assert mu.reg_read(UC_X86_REG_EBX) == 0x1234 and mu.reg_read(UC_X86_REG_ESI) == 0x5678
        assert mu.reg_read(UC_X86_REG_EDI) == FRAME
        fr = {k: r(FRAME + L[k]) for k in ("SURF", "SW", "SH", "PX", "PY")}
        return fr, calls, dict(inbuf=r(IN_BUF), compose=r(COMPOSE), lastv=r(LASTV), ok=r(OV.BSS_OK), buf=r(OV.BSS_BUF))

    def check(name, cond, info):
        nonlocal fails
        print("  %-52s %s" % (name, "ok" if cond else "FAIL %r" % (info,)))
        fails += not cond

    SKY = {(1, 1)}
    px, py = 400 - (400 >> 2), (-40 - (-40 >> 2)) & 0xFFFFFFFF
    fr, c, s = run({0: SKY, 1: set(), 2: set()}, 0)
    check("surface sky -> caverns", c == [("build", 1, 0)] and fr["SURF"] == 0xB0000001 and fr["PX"] == px
          and fr["PY"] == py and s["compose"] == 0 and s["inbuf"] == 0, (fr, c, s))
    fr, c, s = run({0: set(), 1: set(), 2: set()}, 0)
    check("no sky in view -> nothing", c == [] and fr["SURF"] == 0, (fr, c, s))
    fr, c, s = run({0: SKY, 1: set()}, 0, vis=(2, 2, 2, 2))
    check("sky outside the view -> nothing", c == [] and fr["SURF"] == 0, (fr, c, s))
    fr, c, s = run({0: SKY, 1: set()}, 0, vis=(-3, -3, 20, 20))
    check("view larger than the map (clamped)", c == [("build", 1, 0)], (fr, c, s))
    fr, c, s = run({3: SKY, 0: SKY, 1: set(), 2: set()}, 3)
    check("firmament -> surface (through its sky: caverns)",
          c == [("build", 1, 0), ("build", 0, 0xB0000001), ("free", 0xB0000001)] and fr["SURF"] == 0xB0000002
          and s["inbuf"] == 0, (fr, c, s))
    fr, c, s = run({3: SKY, 0: set(), 1: SKY, 2: set()}, 3)
    check("firmament over solid surface -> surface only", c == [("build", 0, 0)], (fr, c, s))
    fr, c, s = run({3: SKY, 0: SKY, 1: SKY, 2: SKY, 4: SKY, 5: set()}, 3)
    check("chain capped at %d" % MAXCHAIN, [x for x in c if x[0] == "build"] ==
          [("build", 4, 0), ("build", 2, 0xB0000001), ("build", 1, 0xB0000002), ("build", 0, 0xB0000003)]
          and fr["SURF"] == 0xB0000004 and len(c) == 7, (fr, c, s))
    fr, c, s = run({0: SKY, 1: set(), 2: set()}, 0, hidden={1})
    check("hidden level skipped", c == [("build", 2, 0)], (fr, c, s))
    fr, c, s = run({0: SKY}, 0)
    check("no level below", c == [] and fr["SURF"] == 0, (fr, c, s))
    fr, c, s = run({0: SKY, 1: set()}, 0, ok=1)
    check("cache valid -> reused", c == [] and fr["SURF"] == 0xAAAA0000 and fr["SW"] == 192, (fr, c, s))
    fr, c, s = run({0: SKY, 1: set()}, 0, ok=1, lastv=3)
    check("level changed -> rebuilt in the old buffer", c == [("build", 1, 0)] and fr["SURF"] == 0xAAAA0000
          and s["lastv"] == 0, (fr, c, s))
    fr, c, s = run({0: SKY, 1: set()}, 0, ok=1, gap=5000)
    check("not drawn for 5 s -> rebuilt", c == [("build", 1, 0)] and fr["SURF"] == 0xAAAA0000, (fr, c, s))
    fr, c, s = run({0: SKY, 1: set()}, 0, ok=1, gap=1900)
    check("1.9 s gap -> reused", c == [], (fr, c, s))
    fr, c, s = run({0: SKY, 1: set()}, 0, compose=(0xC0000000, 384, 96))
    check("compose pass uses the inner cache", c == [] and fr == dict(SURF=0xC0000000, SW=384, SH=96, PX=0, PY=0),
          (fr, c, s))
    fr, c, s = run({0: SKY, 1: set()}, 0, compose=(0, 0, 0))
    check("compose pass without inner cache", c == [] and fr["SURF"] == 0, (fr, c, s))
    fr, c, s = run({0: SKY, 1: set()}, 0, vis=(2, 2, 2, 2), shot=1)
    check("export: whole-level scan, anchored at world 0", c == [("build", 1, 0)] and fr["SURF"] == 0xB0000001
          and fr["PX"] == 0 and fr["PY"] == 0, (fr, c, s))
    fr, c, s = run({0: SKY, 1: set()}, 0, ok=1, gap=5000, shot=1)
    check("export: idle rule off", c == [] and fr["SURF"] == 0xAAAA0000 and fr["PX"] == 0, (fr, c, s))
    print("TEST %s" % ("FAILED" if fails else "passed"))
    return fails


def main():
    if "--test" in sys.argv:
        return 1 if test() else 0
    import pefile
    apply = "--apply" in sys.argv; revert = "--revert" in sys.argv
    if (apply or revert) and SP.busy():
        print("game/editor running - close it first"); return 1
    P, e = build()
    d = open(EPK, "rb").read()
    pe = pefile.PE(data=d)
    rl = {0x55700000 + r.rva for b in pe.DIRECTORY_ENTRY_BASERELOC for r in b.entries if r.type == 3}
    bad = [hex(r) for r in rl if any(va - 3 <= r < va + len(o) for va, o, _ in P)]
    so = ST - 0x558E8000 + pe.sections[1].PointerToRawData
    assert pe.sections[1].Name.startswith(b"DATA") and not any(d[so:so + 0x24]), "state slack not zero"
    P1 = V1.build()[0]
    if all(d[va - B:va - B + len(n)] == n for va, o, n in P1):
        if revert or not apply:
            print("v1 installed - %s" % ("revert it with patch_sky_below_v1.py" if revert else
                                         "dry run OK, --apply upgrades it in place")); return 0
        db = bytearray(d)
        for va, o, n in P1:
            db[va - B:va - B + len(n)] = o
        d = bytes(db)
        with open(EPK, "r+b") as fh:
            for va, o, n in P1:
                fh.seek(va - B); fh.write(o)
        print("v1 removed")
    st = ["vanilla" if d[va - B:va - B + len(o)] == o else "ours" if d[va - B:va - B + len(n)] == n else "OTHER"
          for va, o, n in P]
    print("cave %#x (%d B) + overlay setup + time + 3 builder sites: %s | relocs %s" % (CAVE, len(e["cave"]), st,
                                                                              bad or "none"))
    if "OTHER" in st or bad or len(set(st)) != 1:
        print("ABORT"); return 1
    want = "vanilla" if revert else "ours"
    if st[0] == want:
        print("already %s" % ("reverted" if revert else "applied")); return 0
    if not apply and not revert:
        print("Dry run OK - rerun with --apply (or --revert)."); return 0
    bk = bak_path(EPK, TAG)
    if not revert and not os.path.exists(bk):
        shutil.copy2(EPK, bk)
    with open(EPK, "r+b") as fh:
        for va, o, n in P:
            fh.seek(va - B); fh.write(o if revert else n)
    chk = open(EPK, "rb").read()
    assert all(chk[va - B:va - B + len(o)] == (o if revert else n) for va, o, n in P)
    print("reverted" if revert else "written and verified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
