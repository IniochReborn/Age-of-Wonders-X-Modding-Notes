#!/usr/bin/env python3
r"""
SHOCKWAVE PUSH (vanilla spell 0x7F, 2026-10-18).  AoWTCPCK.dll only.

User: "similar to Gust / Crashing Wave etc, I want the spell Shockwave to push units away by 1 hex (if valid)".

RE (TCAbRangedTE.Execute 0x40B2F8, te = [ebp-4], phase-1 effect loop @0x40B78E over [[0x469420]+0x11C], fx = [ebp-0x20]):
  * Shockwave = ONE long kind-0x2C effect (fx [+0x14] = 0x34 Spellcasting, [+0x18] = 0x7F).  Its damage is dealt by the
    loop's id special case @0x40BCD1: on fx tick [fx+0x10] = 175 / 200 / 225 it broadcasts map msg 0x3100D (caster =
    [te+0x10]) to the hexes CenterHNtoHX(te target [+0x20]/[+0x22], idx) idx 1..6 (ring 1) / 7..18 (ring 2) / 19..36
    (ring 3) - the centre hex (idx 0, the caster) is never hit.  The unit HS handles 0x3100D synchronously
    (TTacticalCombatUnitHS msg handler @0x42144E: GetSpell(0x7F).CreateCA(caster, cu) -> TCombat.ExecuteCombatAction
    -> release), so when the ring-3 broadcast loop exits (0x40BE50 `jmp 0x40CAF2`, 5 B, reloc-free) every hit has resolved
    and dead units are dead.  Everyone in the 3 rings is hit (both sides).
HOOK  PSH 0x40BE50 `jmp 0x40CAF2` -> `jmp psh` (zone below), psh ends with `jmp 0x40CAF2`.
PUSH (deterministic - inside the broadcast TE token on every machine, no RNG):
  1. collect every unit on the 36 ring hexes (FindOwnedChild 0x220104 -> its combat unit [hs+0x1C]; not the caster);
  2. Gust's push (patch_tc_gust_v1.py v8 push_all, copied verbatim apart from the table storage and the centre):
     alive (cu VMT+0x60) and the HS is the unit on its hex; far-to-near from the ring centre; destination = the neighbour
     FARTHEST from the centre (strictly farther than the unit), on the map, no unit and no intact wall / gate section
     (blkchk), and the engine's own per-unit validity (TCombatMoveControlSettings -> TMoveControl.Activate ->
     ValidLocation -> Deactivate); the move = Void Step's cost-0 one-step warp (CreateCombatMoveTE -> Validate ->
     ExecuteDefaultMove).  Invalid -> the unit stays.
  3. for every unit whose hex changed: Gust's hop animation (anim: a kind-0x2F carrier, short shake then MakeArcPathXY
     old -> new; the HS offset preset to the old hex).  The carrier is tagged spell 212 (Gust) so Gust's SPN / LND / SLT
     hooks (patch_tc_gust_v1.py v6+) treat it exactly like a Gust hop: no Winds-of-Fury spin, no landing MoveTo, the
     unit detached at the end, the hop puff = 212's slot 1 = Shockwave's own PARTICLE.ILB orbs.  The carriers sit in the
     strike list, so the TE token waits for them (phase-1 ends only when [map+0x11C] is empty).
  Tables live on the cave's stack frame (no BSS).
Zone AoWTCPCK 0x450400..0x450C00 (verified zero, reloc-free; ally-enchant owns 0x450000..0x450037).
⚠ REQUIRES patch_tc_gust_v1.py (v6+) applied (checked at --apply).  LIFO: revert THIS script before reverting Gust.
Dry-run default; --apply / --revert / --dis / --dll <copy>.  Backup <game>\backup\AoWTCPCK.dll.bak_swpush.
"""
import argparse, os, re, shutil, struct, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file
from patch_airdeath_fix_v1 import asm_pic, relocs
import patch_tc_gust_v1 as G

DLL = game_file("AoWTCPCK.dll")
BASE, V2F = 0x400000, 0x400C00
ZONE, ZONE_END = 0x450400, 0x450C00
SITE, SITE_ORIG = 0x40BE50, bytes.fromhex("e99d0c0000")          # jmp 0x40CAF2 (end of the ring-3 broadcast)
BACK = 0x40CAF2
CARRIER_ID = 212                                                 # Gust: its SPN / LND / SLT hooks own the hop carriers
MAXV = 40                                                        # victims (36 ring hexes)
GUST_SPN, GUST_LND = 0x42BF4D, 0x42BD1E                          # Gust v3+ jmp sites (prerequisite check)
A = dict(G.A, back=BACK, maxv=MAXV, cid=CARRIER_ID)


def src():
    return """
    psh:
        pushad
        call $D
        pop ebx
        sub ebx, $D
        mov esi, [ebp-4]
        call sw_main
        popad
        jmp %(back)#x

    /* sw_main: esi = te, ebx = PIC delta (both preserved).  Frame = Gust's push_all + TAB [ebp-0x100] / DIST [ebp-0x1A0]
       / OLD packed hexes [ebp-0x240] (MAXV dwords each). */
    sw_main:
        push ebp
        mov ebp, esp
        sub esp, 0x250
        push edi
        mov eax, [ebx+%(iat_gp)#x]
        sub eax, %(gp_s)#x
        mov [ebp-0x18], eax
        mov eax, [ebx+%(map)#x]
        mov eax, [eax]
        mov eax, [eax+0x10]
        xor edx, edx
        call %(getmaplevel)#x
        mov [ebp-0x14], eax
        /* centre pixel = the ring centre (te target hex) */
        movzx eax, word ptr [esi+0x20]
        movzx edx, word ptr [esi+0x22]
        call hxp
        mov eax, [ebp-0x48]
        mov [ebp-8], eax
        mov eax, [ebp-0x4c]
        mov [ebp-0xc], eax
        /* collect: the units on ring hexes idx 1..36 */
        mov dword ptr [ebp-0x10], 0
        mov dword ptr [ebp-0x38], 1
    c_loop:
        lea eax, [ebp-0x24]
        push eax
        lea eax, [ebp-0x28]
        push eax
        mov ecx, [ebp-0x38]
        movzx edx, word ptr [esi+0x22]
        movzx eax, word ptr [esi+0x20]
        call %(hn2hx)#x
        mov edx, [ebp-0x24]
        mov ecx, [ebp-0x28]
        call field_at
        test eax, eax
        jz c_next
        mov edx, 0x220104
        mov ecx, [eax]
        call dword ptr [ecx+0x80]
        test eax, eax
        jz c_next
        mov eax, [eax+0x1c]
        test eax, eax
        jz c_next
        cmp eax, [esi+0x10]
        je c_next
        mov ecx, [ebp-0x10]
        cmp ecx, %(maxv)d
        jge c_next
        mov [ebp+ecx*4-0x100], eax
        inc dword ptr [ebp-0x10]
    c_next:
        inc dword ptr [ebp-0x38]
        cmp dword ptr [ebp-0x38], 36
        jle c_loop
        /* distances (-1 = skip) + the old hex of each victim */
        xor edi, edi
    d_loop:
        cmp edi, [ebp-0x10]
        jge d_end
        or dword ptr [ebp+edi*4-0x1a0], -1
        or dword ptr [ebp+edi*4-0x240], -1
        mov eax, [ebp+edi*4-0x100]
        mov [ebp-0x3c], eax
        mov edx, [eax]
        call dword ptr [edx+0x60]
        test al, al
        jz d_next
        call vhex
        test eax, eax
        jz d_next
        call packhex
        mov [ebp+edi*4-0x240], eax
        mov eax, [ebp-0x1c]
        mov edx, [ebp-0x20]
        call hxp
        call dist2
        mov [ebp+edi*4-0x1a0], eax
    d_next:
        inc edi
        jmp d_loop
    d_end:
    p_round:
        or dword ptr [ebp-0x50], -1
        or dword ptr [ebp-0x34], -1
        xor edi, edi
    p_scan:
        cmp edi, [ebp-0x10]
        jge p_pick
        mov eax, [ebp+edi*4-0x1a0]
        cmp eax, [ebp-0x34]
        jle p_sn
        mov [ebp-0x34], eax
        mov [ebp-0x50], edi
    p_sn:
        inc edi
        jmp p_scan
    p_pick:
        mov edi, [ebp-0x50]
        test edi, edi
        js p_done
        mov eax, [ebp+edi*4-0x1a0]
        mov [ebp-0x54], eax
        or dword ptr [ebp+edi*4-0x1a0], -1
        mov eax, [ebp+edi*4-0x100]
        mov [ebp-0x3c], eax
        call vhex
        test eax, eax
        jz p_round
        call push_one
        jmp p_round
    p_done:
        /* the hop animation for every victim whose hex changed */
        xor edi, edi
    a_loop:
        cmp edi, [ebp-0x10]
        jge a_end
        cmp dword ptr [ebp+edi*4-0x240], -1
        je a_next
        mov eax, [ebp+edi*4-0x100]
        mov [ebp-0x3c], eax
        mov edx, [eax]
        call dword ptr [edx+0x60]
        test al, al
        jz a_next
        call vhex
        test eax, eax
        jz a_next
        call packhex
        mov edx, [ebp+edi*4-0x240]
        cmp eax, edx
        je a_next
        push esi
        push edi
        mov esi, [ebp-0x3c]
        call anim
        pop edi
        pop esi
    a_next:
        inc edi
        jmp a_loop
    a_end:
        pop edi
        mov esp, ebp
        pop ebp
        ret

    /* packhex: [ebp-0x1c]/[ebp-0x20] -> eax = x | y << 16 (Gust's hexof layout) */
    packhex:
        mov eax, [ebp-0x20]
        shl eax, 16
        mov ecx, [ebp-0x1c]
        and ecx, 0xffff
        or eax, ecx
        ret

    /* ---- verbatim from patch_tc_gust_v1.py (zone 1 push_all helpers) ---- */
    vhex:
        mov eax, [ebp-0x3c]
        mov eax, [eax+0x60]
        test eax, eax
        jz vh_no
        mov edx, [eax]
        call dword ptr [edx+0x74]
        movsx eax, al
        mov [ebp-0x1c], eax
        mov eax, [ebp-0x3c]
        mov eax, [eax+0x60]
        mov edx, [eax]
        call dword ptr [edx+0x78]
        movsx eax, al
        mov [ebp-0x20], eax
        mov eax, [ebp-0x3c]
        mov eax, [eax+0x60]
        mov edx, [eax]
        call dword ptr [edx+0x24]
        cmp eax, 0x220104
        jne vh_no
        mov al, 1
        ret
    vh_no:
        xor eax, eax
        ret

    field_at:
        test edx, edx
        js fa_no
        test ecx, ecx
        js fa_no
        mov eax, [ebp-0x14]
        cmp edx, [eax+0xc]
        jge fa_no
        cmp ecx, [eax+0x10]
        jge fa_no
        call %(getfield)#x
        ret
    fa_no:
        xor eax, eax
        ret

    hxp:
        lea ecx, [ebp-0x4c]
        push ecx
        lea ecx, [ebp-0x48]
        call %(hxtohp)#x
        ret

    dist2:
        mov eax, [ebp-0x48]
        sub eax, [ebp-8]
        imul eax, eax
        mov ecx, [ebp-0x4c]
        sub ecx, [ebp-0xc]
        imul ecx, ecx
        add eax, ecx
        ret

    blkchk:
        push esi
        mov esi, eax
        mov edx, 0x220104
        mov ecx, [esi]
        call dword ptr [ecx+0x80]
        test eax, eax
        jnz bk_out
        mov eax, esi
        mov edx, 0x220504
        mov ecx, [esi]
        call dword ptr [ecx+0x80]
        test eax, eax
        jz bk_gate
        cmp dword ptr [eax+0x20], 0
        jg bk_out
    bk_gate:
        mov eax, esi
        mov edx, 0x220506
        mov ecx, [esi]
        call dword ptr [ecx+0x80]
        test eax, eax
        jz bk_out
        cmp dword ptr [eax+0x20], 0
        jg bk_out
        xor eax, eax
    bk_out:
        pop esi
        ret

    push_one:
        mov eax, [ebp-0x54]
        mov [ebp-0x34], eax
        or dword ptr [ebp-0x2c], -1
        mov dword ptr [ebp-0x38], 1
    po_hn:
        lea eax, [ebp-0x24]
        push eax
        lea eax, [ebp-0x28]
        push eax
        mov ecx, [ebp-0x38]
        mov edx, [ebp-0x20]
        mov eax, [ebp-0x1c]
        call %(hn2hx)#x
        mov edx, [ebp-0x24]
        mov ecx, [ebp-0x28]
        call field_at
        test eax, eax
        jz po_next
        mov eax, [ebp-0x24]
        mov edx, [ebp-0x28]
        call hxp
        call dist2
        cmp eax, [ebp-0x34]
        jle po_next
        mov [ebp-0x34], eax
        mov eax, [ebp-0x24]
        mov [ebp-0x2c], eax
        mov eax, [ebp-0x28]
        mov [ebp-0x30], eax
    po_next:
        inc dword ptr [ebp-0x38]
        cmp dword ptr [ebp-0x38], 6
        jle po_hn
        cmp dword ptr [ebp-0x2c], -1
        je po_ret
        mov edx, [ebp-0x2c]
        mov ecx, [ebp-0x30]
        call field_at
        call blkchk
        test eax, eax
        jnz po_ret
        xor ecx, ecx
        mov dl, 1
        mov eax, [ebx+%(setcls)#x]
        call %(setcreate)#x
        mov [ebp-0x40], eax
        mov edi, eax
        push 0
        mov ecx, [ebp-0x20]
        mov edx, [ebp-0x1c]
        mov eax, edi
        call %(setsrcpos)#x
        mov eax, [ebp-0x3c]
        mov edx, [eax+0x60]
        mov [edi+0x9c], edx
        mov byte ptr [edi+0x1ac], 0x1a
        mov byte ptr [edi+0x65], 0
        lea edx, [edi+0xac]
        mov eax, [ebp-0x3c]
        mov eax, [eax+0x4c]
        call %(cmptable)#x
        mov eax, [ebp-0x3c]
        call %(getplayer)#x
        mov [edi+0x6c], al
        mov dword ptr [edi+0x98], 0xc8
        mov eax, [ebx+%(tcg)#x]
        mov eax, [eax+0xfc]
        mov [ebp-0x44], eax
        mov dword ptr [ebp-0x5c], 0
        mov edx, edi
        mov ecx, [ebp-0x18]
        add ecx, %(ep_act)#x
        call ecx
        test al, al
        jz po_rel
        mov eax, [ebp-0x44]
        mov edx, [ebp-0x40]
        mov ecx, [edx+0x9c]
        mov [eax+0x1e0], ecx
        mov cl, [edx+0x1ac]
        mov [eax+0x1e4], cl
        push 0
        mov ecx, [ebp-0x30]
        mov edx, [ebp-0x2c]
        mov eax, [ebp-0x44]
        mov edi, [ebp-0x18]
        add edi, %(ep_valid)#x
        call edi
        movzx eax, al
        mov [ebp-0x5c], eax
        mov eax, [ebp-0x44]
        mov ecx, [ebp-0x18]
        add ecx, %(ep_deact)#x
        call ecx
    po_rel:
        mov eax, [ebp-0x40]
        call %(setrelease)#x
        cmp dword ptr [ebp-0x5c], 0
        je po_ret
        mov dl, 1
        mov eax, [ebx+%(xylcls)#x]
        call %(xylcreate)#x
        mov edi, eax
        mov [ebp-0x58], eax
        mov edx, [ebp-0x30]
        shl edx, 8
        or edx, [ebp-0x2c]
        mov eax, edi
        call %(xyladd)#x
        mov edx, [ebp-0x20]
        shl edx, 8
        or edx, [ebp-0x1c]
        mov eax, edi
        call %(xyladd)#x
        mov edx, edi
        mov eax, [ebp-0x3c]
        call %(createmovete)#x
        test eax, eax
        jz po_freepath
        push eax
        call %(validate)#x
        test al, al
        pop eax
        jz po_freete
        push eax
        mov dword ptr [eax+0x18], 1
        call %(execdefmove)#x
        pop eax
    po_freete:
        call %(objfree)#x
    po_freepath:
        mov eax, [ebp-0x58]
        call %(objfree)#x
    po_ret:
        ret

    /* ---- verbatim from patch_tc_gust_v1.py zone 3 (addpt / anim); setid_edi -> a fixed Gust tag ---- */
    addpt:
        push eax
        push edx
        mov dl, 1
        mov eax, [ebx+%(txyz)#x]
        call %(tobjcreate)#x
        pop edx
        mov [eax+8], edx
        pop edx
        mov [eax+4], edx
        mov edx, eax
        mov eax, [edi+0x1c]
        call %(xyzadd)#x
        ret

    anim:
        push ebp
        mov ebp, esp
        sub esp, 0x30
        push edi
        mov [ebp-0x04], eax
        mov [ebp-0x08], edx
        lea ecx, [ebp-0x10]
        push ecx
        lea ecx, [ebp-0x0c]
        movsx eax, word ptr [ebp-0x08]
        movsx edx, word ptr [ebp-0x06]
        call %(hxtohp)#x
        lea ecx, [ebp-0x18]
        push ecx
        lea ecx, [ebp-0x14]
        movsx eax, word ptr [ebp-0x04]
        movsx edx, word ptr [ebp-0x02]
        call %(hxtohp)#x
        add dword ptr [ebp-0x0c], 16
        add dword ptr [ebp-0x10], 16
        add dword ptr [ebp-0x14], 16
        add dword ptr [ebp-0x18], 16
        mov eax, [ebx+%(gmap)#x]
        mov dl, 0x2f
        call %(addfx)#x
        mov edi, eax
        mov dword ptr [edi+0x14], 0x34
        mov dword ptr [edi+0x18], %(cid)d
        mov [edi+0x2c], esi
        mov dword ptr [edi+0x24], -5
        mov dword ptr [edi+0x28], -5
        mov dword ptr [edi+0x10], 20
        mov eax, [ebp-0x14]
        mov edx, [ebp-0x18]
        call addpt
        mov dword ptr [ebp-0x1c], 0
    an_sh:
        mov ecx, [ebp-0x1c]
        cmp ecx, %(shake)d
        jge an_shd
        mov eax, ecx
        shr eax, 2
        neg eax
        add eax, 4
        test cl, 1
        jz an_pos
        neg eax
    an_pos:
        add eax, [ebp-0x0c]
        mov edx, [ebp-0x10]
        call addpt
        inc dword ptr [ebp-0x1c]
        jmp an_sh
    an_shd:
        mov eax, [ebp-0x14]
        sub eax, [ebp-0x0c]
        cdq
        xor eax, edx
        sub eax, edx
        mov ecx, eax
        mov eax, [ebp-0x18]
        sub eax, [ebp-0x10]
        cdq
        xor eax, edx
        sub eax, edx
        add eax, ecx
        xor edx, edx
        mov ecx, %(hoppts)d
        div ecx
        cmp eax, 1
        jge an_div
        mov eax, 1
    an_div:
        push dword ptr [ebp-0x18]
        push eax
        push %(hoph)d
        lea eax, [edi+0x1c]
        push eax
        mov eax, [ebp-0x0c]
        mov edx, [ebp-0x10]
        mov ecx, [ebp-0x14]
        call %(mkarc)#x
        mov eax, [esi+0x60]
        mov edx, [ebp-0x0c]
        sub edx, [ebp-0x14]
        mov [eax+0x2c], edx
        mov edx, [ebp-0x10]
        sub edx, [ebp-0x18]
        mov [eax+0x30], edx
        mov byte ptr [eax+0x44], 1
        pop edi
        mov esp, ebp
        pop ebp
        ret
    """ % A


def build():
    s = re.sub(r"/\*.*?\*/", "", src(), flags=re.S)
    blob = asm_pic(s, ZONE)
    assert ZONE + len(blob) <= ZONE_END, hex(ZONE + len(blob))
    return blob


def site_state(d):
    b = bytes(d[SITE - V2F:SITE - V2F + 5])
    if b == SITE_ORIG: return "vanilla"
    if b[0] == 0xE9 and SITE + 5 + struct.unpack_from("<i", b, 1)[0] == ZONE: return "ours"
    return "OTHER"


def gust_ok(d):
    for s in (GUST_SPN, GUST_LND):
        b = d[s - V2F:s - V2F + 5]
        if b[0] != 0xE9: return False
        t = s + 5 + struct.unpack_from("<i", b, 1)[0]
        if not (G.ZONE3 <= t < G.ZONE3_END): return False
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true"); ap.add_argument("--revert", action="store_true")
    ap.add_argument("--dis", action="store_true"); ap.add_argument("--dll", default=DLL)
    a = ap.parse_args()
    path = a.dll; d = bytearray(open(path, "rb").read())
    R = relocs(d, BASE)
    zr = [hex(r) for r in R if ZONE - 3 <= r < ZONE_END]; sr = [hex(r) for r in R if SITE - 3 <= r < SITE + 5]
    zone = bytes(d[ZONE - V2F:ZONE_END - V2F]); st = site_state(d); blob = build()
    print("AoWTCPCK shockwave site %#x %s | zone %#x %s (%d B code) | gust hop hooks %s | relocs zone %s site %s" % (
        SITE, st, ZONE, "zero" if zone == bytes(len(zone)) else ("ours" if zone[:len(blob)] == blob else "used"), len(blob),
        "ok" if gust_ok(d) else "MISSING", zr or "none", sr or "none"))
    if zr or sr: print("ABORT: relocations in the zone / under the site"); return 1
    if st == "OTHER": print("ABORT: the site holds unknown code"); return 1
    if a.revert:
        if st != "ours": print("already reverted"); return 0
        d[SITE - V2F:SITE - V2F + 5] = SITE_ORIG; d[ZONE - V2F:ZONE_END - V2F] = bytes(ZONE_END - ZONE)
        open(path, "r+b").write(d); print("reverted", path); return 0
    same = st == "ours" and zone[:len(blob)] == blob and zone[len(blob):] == bytes(len(zone) - len(blob))
    if same:
        if a.dis: dis(d)
        print("already applied"); return 0
    if st == "vanilla" and zone != bytes(len(zone)): print("ABORT: zone not free"); return 1
    if st == "ours": print("older build found -> rewriting the zone in place")
    if not gust_ok(d): print("ABORT: patch_tc_gust_v1.py (v3+ SPN / LND hop hooks) is not applied - the hop carriers need it"); return 1
    if not a.apply: print("Dry run OK - rerun with --apply (or --revert)."); return 0
    if os.path.abspath(path) == os.path.abspath(DLL):
        bak = bak_path(DLL, ".bak_swpush")
        if not os.path.exists(bak): shutil.copy2(DLL, bak); print("backup ->", bak)
    d[ZONE - V2F:ZONE_END - V2F] = bytes(ZONE_END - ZONE); d[ZONE - V2F:ZONE - V2F + len(blob)] = blob
    d[SITE - V2F:SITE - V2F + 5] = b"\xE9" + struct.pack("<i", ZONE - (SITE + 5))
    open(path, "r+b").write(d); print("written", path)
    if a.dis: dis(d)
    return 0


def dis(d):
    from capstone import Cs, CS_ARCH_X86, CS_MODE_32
    md = Cs(CS_ARCH_X86, CS_MODE_32)
    for i in md.disasm(bytes(d[ZONE - V2F:ZONE_END - V2F]), ZONE):
        if i.bytes == b"\x00\x00": break
        print("%08X  %-8s %s" % (i.address, i.mnemonic, i.op_str))


if __name__ == "__main__":
    sys.exit(main())
