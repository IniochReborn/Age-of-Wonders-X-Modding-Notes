#!/usr/bin/env python3
r"""
AoWTCPCK.dll: Seeker Bolts (ability 0x3A) v2 (2026-10-18) - supersedes patch_tc_seekerbolts_v1.py (upgrades it in place).

ROOT CAUSE of v1 "nothing new shows" (user 10/18: no start-up spin, bolt looks like before, no blue, no hit burst):
the shot is NOT a kind-6 TfxHS.  A unit ranged attack's fx kind comes from TCPCK's ability->kind table (DATA 0x467248,
read via [0x4693DC] at 0x409D07 by the ranged-attack CA, stored at [ca+0x60] and passed to AddEffect 0x40A170): ability
0x3A -> kind **1** (same as Archery 0x16 / Javelin 0x39; Magic Bolts 0x79 = 3, CreateHurl's cl = 6 is something else).
Every v1 cave tested `[fx+0x34] == 6`, so none of them ever fired; and Show kind 1 (0x42FAA3) picks the gfx slot from
[fx+0x20] = the flight DIRECTION (0..23 - that is why the vanilla record has 24 identical BOLTS slots), so the new head
only appeared for directions 0/1 and directions 2/3 drew the spin/impact sequences as the "bolt"; no trail is drawn.
The kind table must NOT change: 0x467248 is read by ~12 AI/CA sites that treat kinds 1-3 as ranged.

v2 = v1's caves with the kind test 6 -> 1 (KIND), plus one more hook:
  SHW  0x42F9CB (7 B `movzx eax,byte [eax+0x34] / cmp eax,0x30`, inside TfxHS.Show 0x42F978): a kind-1 fx with
       [+0x14] == 0x3A is DISPATCHED as kind 6 (0x42FB2A: slot 0 = head at a fixed slot, the 0x43CB70 Hellfire gate
       ([+0x18] is 0 for ability shots), slot 1 = trail, then the shared 0x42F8E8).  The fx keeps kind 1 everywhere else
       (NewFrame speed, CA, AI).
v1 notes still apply (below).  Revert v2 with THIS script (--revert -> vanilla sites, zone zeroed, slot chain head back
to prev); v1 --revert would see the v2 zone as FOREIGN and abort.

v1 RE: TfxHS (VMT 0x412028, InstanceSize 0x38; +0x10 path index (starts -1), +0x14 ability id, +0x18 spell id, +0x1C TXYZ
path list, +0x20 direction slot (kind 1), +0x2C target, +0x34 kind byte, +0x35..+0x37 PADDING = zero at creation, never
read).  NewFrame (0x429E78) adds 1 to +0x10 every tick (0x429ED5) and kinds 1/2/3/5/6/0xD share 0x429FBB, which adds one
more for 0x3A; at the path end (0x42A04F..) it plays cue 1 of the ability's sound list and finishes.  The ranged CA waits
for [fx+0xC] (finished) at 0x40A5CF, so holding the index delays the damage with the bolt.  A kind-0x26 TfxHS
(AddEffect 0x41C6EC) plays one gfx slot once at its XYZ for frames x (f18+1) ticks and dies (non-spell path: slot
`mov edx,1` @0x42A613; Show [0x26] -> SUB_0042E4C4(1)).
Hooks (PIC, zone 0x44F000-0x44F400):
  NF6  0x429FBB (6 B): a kind-1 0x3A bolt is HELD for HOLD ticks: [fx+0x35] counts the ticks, [fx+0x10] pinned to 0,
       exit through 0x42E3A3.  Tick 1: K = the first path point >= LAUNCH_PX from point 0 (capped at count/3) ->
       [fx+0x36]; spawn a kind-0x26 helper there ([+0x14] = 0x3A, [+0x18] = MARK_SPIN) = the orb spin-up (gfx slot 2).
       Tick HOLD: release at index K and play cue 2 (SEEKER_LAUNCH) if sounds are on ([map+0x129]).
  HIT  0x42A0D3 (6 B, the arrival join after cue 1): spawn a kind-0x26 helper MARK_HIT at the last path point (slot 3).
  N26  0x42A613 (5 B `mov edx,1` -> call): a 0x3A helper's NewFrame lifetime uses slot 2 / 3 by its marker.
  SLT  0x42E4C4 (chain head, prev decoded at apply): 0x3A kind-0x26 helpers draw slot 2 / 3; a held kind-1 0x3A bolt
       ([fx+0x10] == 0) draws index 0x7F = no sequence (GetImageSequence returns nil out of range) -> hidden.
Timing is deterministic (no RNG; sound only behind the sound-on gate) -> MP-safe.
LIFO: the SLT site is a chain head - revert this BEFORE re-running gust / soulsiphon / Ashes / Hellfire.
Dry-run default; --apply / --revert / --dll <copy>.  Backup <game>\backup\AoWTCPCK.dll.bak_seeker2.
"""
import argparse, os, shutil, struct, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file
import patch_tc_banshee_vortex_v1 as BV
import patch_tc_seekerbolts_v1 as V1
from patch_tc_hellfire_portal_v1 import asm_delta

V2F = 0x400C00
ZONE, ZONE_END = 0x44F000, 0x44F400
ABIL = 0x3A
KIND = 1                     # the shot's TfxHS kind (TCPCK ability->kind table 0x467248[0x3A]); v1 wrongly assumed 6
HOLD = 30                    # ticks the bolt waits (~0.87 s at ~34.5 ticks/s) = the spin sequence length (30 frames x 1 tick)
LAUNCH_PX = 20               # the orbs spin this far in front of the caster, along the shot
MARK_SPIN, MARK_HIT = 0x3A01, 0x3A02          # helper [fx+0x18] markers (far above any spell id)
SLOT_SPIN, SLOT_HIT, SLOT_NONE = 2, 3, 0x7F
CUE_LAUNCH = 2
MAP, REG, TXYZ_IAT = 0x46C064, 0x46E8D0, 0x46EB24
GETABILITY, SFXPLAY = 0x402704, 0x4022F4
COUNT, GETXYZ, XYZADD, ADDEFFECT, TOBJCREATE = 0x402DFC, 0x402DF4, 0x402DE4, 0x41C6EC, 0x401040
EXIT_INFLIGHT = 0x42E3A3
NF6, NF6_ORIG, NF6_BACK = 0x429FBB, bytes.fromhex("8b45f88b4014"), 0x429FC1
HIT, HIT_ORIG, HIT_BACK = 0x42A0D3, bytes.fromhex("8b45f88b401c"), 0x42A0D9
N26, N26_ORIG = 0x42A613, bytes.fromhex("ba01000000")
SLT, SLT_VANILLA, SLT_RESUME = 0x42E4C4, bytes.fromhex("558bec518945fc"), 0x42E4CB
SHW, SHW_ORIG, SHW_BACK = 0x42F9CB, bytes.fromhex("0fb6403483f830"), 0x42F9D2
BAK_SUFFIX = ".bak_seeker2"


def build(prev):
    """prev = the slot chain's previous head target (None = the site was vanilla)."""
    out = bytearray(); where = {}
    P = {"abil": ABIL, "hold": HOLD, "exit": EXIT_INFLIGHT, "map": MAP, "reg": REG, "txyz": TXYZ_IAT,
         "getab": GETABILITY, "play": SFXPLAY, "count": COUNT, "getxyz": GETXYZ, "xyzadd": XYZADD, "add": ADDEFFECT,
         "create": TOBJCREATE, "px2": LAUNCH_PX * LAUNCH_PX, "mspin": MARK_SPIN, "mhit": MARK_HIT, "sspin": SLOT_SPIN,
         "shit": SLOT_HIT, "snone": SLOT_NONE, "kind": KIND, "shwback": SHW_BACK, "cue": CUE_LAUNCH, "nf6back": NF6_BACK, "hitback": HIT_BACK}

    def place(name, src):
        while len(out) % 16: out.append(0)
        va = ZONE + len(out); where[name] = va
        out.extend(asm_delta(src % dict(P, **{k: v for k, v in where.items()}), va))

    # findk: esi = bolt -> eax = K (the first path point >= LAUNCH_PX px from point 0 on screen, capped at count/3)
    place("findk", """
        push ebx
        push edi
        push ebp
        mov eax, [esi+0x1c]
        call %(count)#x
        xor edx, edx
        mov ecx, 3
        div ecx
        mov ebp, eax
        cmp ebp, 255
        jbe fk_c
        mov ebp, 255
    fk_c:
        mov eax, [esi+0x1c]
        xor edx, edx
        call %(getxyz)#x
        mov ecx, [eax+4]
        mov edx, [eax+8]
        sub edx, [eax+0xc]
        push edx
        push ecx
        mov ebx, 1
    fk_loop:
        cmp ebx, ebp
        jge fk_cap
        mov eax, [esi+0x1c]
        mov edx, ebx
        call %(getxyz)#x
        mov ecx, [eax+4]
        sub ecx, [esp]
        mov edx, [eax+8]
        sub edx, [eax+0xc]
        sub edx, [esp+4]
        imul ecx, ecx
        imul edx, edx
        add ecx, edx
        cmp ecx, %(px2)d
        jge fk_done
        inc ebx
        jmp fk_loop
    fk_cap:
        mov ebx, ebp
    fk_done:
        mov eax, ebx
        add esp, 8
        pop ebp
        pop edi
        pop ebx
        ret
    """)
    # spawn: esi = bolt, edi = path index, ecx = marker, ebx = PIC delta -> a kind-0x26 helper at that point
    place("spawn", """
        push esi
        push edi
        push ebp
        push ecx
        mov eax, [esi+0x1c]
        mov edx, edi
        call %(getxyz)#x
        mov ecx, [eax+4]
        mov edx, [eax+8]
        sub edx, [eax+0xc]
        push edx
        push ecx
        mov eax, [ebx+%(map)#x]
        mov dl, 0x26
        call %(add)#x
        mov ebp, eax
        mov dl, 1
        mov eax, [ebx+%(txyz)#x]
        call %(create)#x
        mov edx, eax
        mov eax, [ebp+0x1c]
        call %(xyzadd)#x
        mov eax, [ebp+0x1c]
        xor edx, edx
        call %(getxyz)#x
        pop ecx
        mov [eax+4], ecx
        pop edx
        mov [eax+8], edx
        mov dword ptr [eax+0xc], 0
        mov dword ptr [ebp+0x14], %(abil)d
        pop ecx
        mov [ebp+0x18], ecx
        mov dword ptr [ebp+0x2c], 0
        pop ebp
        pop edi
        pop esi
        ret
    """)
    place("nf6", """
        mov eax, [ebp-8]
        cmp dword ptr [eax+0x14], %(abil)d
        jne nf_van
        cmp byte ptr [eax+0x34], %(kind)d
        jne nf_van
        cmp byte ptr [eax+0x35], %(hold)d
        jae nf_van
        push ebx
        push esi
        push edi
        mov esi, eax
        call $D
        pop ebx
        sub ebx, $D
        inc byte ptr [esi+0x35]
        mov dword ptr [esi+0x10], 0
        cmp byte ptr [esi+0x35], 1
        jne nf_rel
        call %(findk)#x
        mov byte ptr [esi+0x36], al
        mov edi, eax
        mov ecx, %(mspin)d
        call %(spawn)#x
    nf_rel:
        cmp byte ptr [esi+0x35], %(hold)d
        jne nf_out
        movzx eax, byte ptr [esi+0x36]
        mov [esi+0x10], eax
        mov eax, [ebx+%(map)#x]
        cmp byte ptr [eax+0x129], 0
        je nf_out
        mov eax, [ebx+%(reg)#x]
        mov eax, [eax]
        mov eax, [eax+0x80]
        mov edx, %(abil)d
        call %(getab)#x
        mov eax, [eax+0x18]
        mov edx, %(cue)d
        call %(play)#x
    nf_out:
        pop edi
        pop esi
        pop ebx
        jmp %(exit)#x
    nf_van:
        mov eax, [eax+0x14]
        jmp %(nf6back)#x
    """)
    place("hit", """
        mov eax, [ebp-8]
        cmp dword ptr [eax+0x14], %(abil)d
        jne h_van
        cmp byte ptr [eax+0x34], %(kind)d
        jne h_van
        push ebx
        push esi
        push edi
        mov esi, eax
        call $D
        pop ebx
        sub ebx, $D
        mov eax, [esi+0x1c]
        call %(count)#x
        lea edi, [eax-1]
        test edi, edi
        jl h_skip
        mov ecx, %(mhit)d
        call %(spawn)#x
    h_skip:
        pop edi
        pop esi
        pop ebx
        mov eax, [ebp-8]
    h_van:
        mov eax, [eax+0x1c]
        jmp %(hitback)#x
    """)
    place("n26", """
        mov edx, 1
        push ecx
        mov ecx, [ebp-8]
        cmp dword ptr [ecx+0x14], %(abil)d
        jne n_out
        cmp dword ptr [ecx+0x18], %(mspin)d
        jne n_hit
        mov edx, %(sspin)d
        jmp n_out
    n_hit:
        cmp dword ptr [ecx+0x18], %(mhit)d
        jne n_out
        mov edx, %(shit)d
    n_out:
        pop ecx
        ret
    """)
    # shw: TfxHS.Show kind dispatch - a kind-1 0x3A bolt is drawn by the kind-6 case (fixed head slot 0 + trail slot 1)
    place("shw", """
        cmp dword ptr [eax+0x14], %(abil)d
        movzx eax, byte ptr [eax+0x34]
        jne w_out
        cmp eax, %(kind)d
        jne w_out
        mov eax, 6
    w_out:
        cmp eax, 0x30
        jmp %(shwback)#x
    """)
    tail = ("jmp %#x" % prev) if prev is not None else (
        ".byte " + ", ".join("%#x" % x for x in SLT_VANILLA) + "\n        jmp %#x" % SLT_RESUME)
    place("slot", """
        push ecx
        mov ecx, [esp+8]
        mov ecx, [ecx-4]
        cmp dword ptr [ecx+0x14], %(abil)d
        jne s_out
        cmp byte ptr [ecx+0x34], %(kind)d
        jne s_26
        cmp dword ptr [ecx+0x10], 0
        jne s_out
        mov eax, %(snone)d
        jmp s_out
    s_26:
        cmp byte ptr [ecx+0x34], 0x26
        jne s_out
        cmp eax, 1
        jne s_out
        cmp dword ptr [ecx+0x18], %(mspin)d
        jne s_hit
        mov eax, %(sspin)d
        jmp s_out
    s_hit:
        cmp dword ptr [ecx+0x18], %(mhit)d
        jne s_out
        mov eax, %(shit)d
    s_out:
        pop ecx
    """ + "    " + tail + "\n")
    assert ZONE + len(out) <= ZONE_END, hex(ZONE + len(out))
    return bytes(out), where


def jmp(src, dst, n): return b"\xe9" + struct.pack("<i", dst - (src + 5)) + b"\x90" * (n - 5)
def call(src, dst): return b"\xe8" + struct.pack("<i", dst - (src + 5))


def decode_zone(zone):
    """Which of our layouts sits in the zone and its slot-chain prev: ('v2'|'v1', prev) or (None, None)."""
    for tag, B in (("v2", build), ("v1", V1.build)):
        body, _ = B(None)
        if zone[:len(body)] == body and not any(zone[len(body):]): return tag, None
        bj, _ = B(SLT_RESUME); at = len(bj) - 5
        if zone[at] != 0xE9: continue
        prev = ZONE + at + 5 + struct.unpack_from("<i", zone, at + 1)[0]
        body, _ = B(prev)
        if zone[:len(body)] == body and not any(zone[len(body):]): return tag, prev
    return None, None


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--apply", action="store_true"); ap.add_argument("--revert", action="store_true")
    ap.add_argument("--dll", default=game_file("AoWTCPCK.dll")); a = ap.parse_args()
    d = bytearray(open(a.dll, "rb").read())
    f = lambda va, n: bytes(d[va - V2F:va - V2F + n])
    zone = f(ZONE, ZONE_END - ZONE)
    ver, zprev = decode_zone(zone) if any(zone) else (None, None)
    zst = "zero" if not any(zone) else ver or "FOREIGN"
    # the slot chain head: vanilla, someone else's head (= our prev), or ours (prev recovered from our cave's tail)
    sb = f(SLT, 7); prev = None; slot_state = "vanilla"
    if sb != SLT_VANILLA:
        if sb[0] != 0xE9 or sb[5:] != b"\x90\x90": print("ABORT - slot site %#x unexpected: %s" % (SLT, sb.hex())); return 1
        t = SLT + 5 + struct.unpack_from("<i", sb, 1)[0]
        if ZONE <= t < ZONE_END:
            if ver is None: print("ABORT - slot head points into the zone but the zone is %s" % zst); return 1
            slot_state = "ours(%s)" % ver; prev = zprev
        else:
            slot_state = "chain(prev %#x)" % t; prev = t
    cave, where = build(prev)
    _, w1 = V1.build(prev)
    def st(va, n, van, v2b, v1b):
        cur = f(va, n)
        return "vanilla" if cur == van else "v2" if cur == v2b else "v1" if v1b is not None and cur == v1b else "OTHER(%s)" % cur.hex()
    nf6 = st(NF6, 6, NF6_ORIG, jmp(NF6, where["nf6"], 6), jmp(NF6, w1["nf6"], 6))
    hit = st(HIT, 6, HIT_ORIG, jmp(HIT, where["hit"], 6), jmp(HIT, w1["hit"], 6))
    n26 = st(N26, 5, N26_ORIG, call(N26, where["n26"]), call(N26, w1["n26"]))
    shw = st(SHW, 7, SHW_ORIG, jmp(SHW, where["shw"], 7), None)
    rl = BV.reloc_set(bytes(d))
    bad = sorted(hex(r) for r in rl if ZONE - 3 <= r < ZONE_END or NF6 - 3 <= r < NF6 + 6 or HIT - 3 <= r < HIT + 6
                 or N26 - 3 <= r < N26 + 5 or SLT - 3 <= r < SLT + 7 or SHW - 3 <= r < SHW + 7)
    print("nf6 %s | hit %s | n26 %s | shw %s | slot head %s | zone %#x-%#x %s (v2 cave %d B) | relocs %s" % (
        nf6, hit, n26, shw, slot_state, ZONE, ZONE_END, zst, len(cave), bad or "none"))
    if any(x.startswith("OTHER") for x in (nf6, hit, n26, shw)) or zst == "FOREIGN" or bad:
        print("ABORT"); return 1
    ours = slot_state.startswith("ours")
    if a.revert:
        if not ours and nf6 == hit == n26 == shw == "vanilla" and zst == "zero": print("not applied"); return 0
        d[NF6 - V2F:NF6 - V2F + 6] = NF6_ORIG; d[HIT - V2F:HIT - V2F + 6] = HIT_ORIG; d[N26 - V2F:N26 - V2F + 5] = N26_ORIG
        d[SHW - V2F:SHW - V2F + 7] = SHW_ORIG
        if ours: d[SLT - V2F:SLT - V2F + 7] = SLT_VANILLA if prev is None else jmp(SLT, prev, 7)
        d[ZONE - V2F:ZONE_END - V2F] = bytes(ZONE_END - ZONE)
    else:
        if slot_state == "ours(v2)" and nf6 == hit == n26 == shw == "v2" and zst == "v2": print("already applied"); return 0
        if zst == "v1": print("upgrading v1 -> v2 in place")
        d[ZONE - V2F:ZONE_END - V2F] = bytes(ZONE_END - ZONE); d[ZONE - V2F:ZONE - V2F + len(cave)] = cave
        d[NF6 - V2F:NF6 - V2F + 6] = jmp(NF6, where["nf6"], 6); d[HIT - V2F:HIT - V2F + 6] = jmp(HIT, where["hit"], 6)
        d[N26 - V2F:N26 - V2F + 5] = call(N26, where["n26"]); d[SLT - V2F:SLT - V2F + 7] = jmp(SLT, where["slot"], 7)
        d[SHW - V2F:SHW - V2F + 7] = jmp(SHW, where["shw"], 7)
    for k in sorted(where): print("  %-6s %#x" % (k, where[k]))
    if not (a.apply or a.revert): print("Dry run OK - rerun with --apply (or --revert)."); return 0
    b = bak_path(a.dll, BAK_SUFFIX)
    if not os.path.exists(b): shutil.copy2(a.dll, b); print("backup ->", b)
    BV.write_inplace(a.dll, bytes(d)); assert open(a.dll, "rb").read() == bytes(d)
    print("written and verified"); return 0


if __name__ == "__main__":
    sys.exit(main())
