#!/usr/bin/env python3
r"""
AIR/DEATH FIXES (2026-10-15).  AoWEPACK.dll + AoWTCPCK.dll.

A) 345 SUFFOCATE (TVaporize clone, class 7, 5 strikes) - user: "should not be able to target undead or machines".
   Invalid target = machine (TUnit VMT+0x114 GetUnitType == 2) OR undead (race VMT+0xA4 == 0x0B or HasAbility
   VMT+0x148 (0x81)) - the vanilla Turn Undead test (TTurnUndead.CreateCA 0x557F7C50).  Five hooks, all keyed on 345:
     AoWEPACK
       EX  0x557F6A2A  TCombatSpellCA.Execute `call TDamageCA.Execute` - CHAINED in front of patch_bloodboil_v1's ex
           cave (0x5585F050): 345 + invalid target -> damage byte [ca+0x10] := 0, then TDamageCA.Execute 0x55729D14;
           any other spell -> jmp the previous cave (unchanged behaviour).  Safety net for every cast path.
       AI  0x557F744F  TCombatSpell.GetCombatDamageValueEx (tactical AI scorer, ebx spell / esi target / edi out) -
           CHAINED in front of Blood Boil's ai cave: call it (it replays the 5 overwritten bytes), then 345 + invalid
           target -> expected [edi] / max [edi+4] := 0.
       FC  0x557F76A5  TVaporize fcGetDamageValueEx epilogue (fast/auto combat scorer 0x557F7464, ebx spell / edi
           target / esi out; `pop edi/pop esi/pop ebx/mov esp,ebp`, 5 B) -> jmp cave: 345 + invalid -> [esi] = [esi+4]
           = 0 (fcPrefetchCombatCommands drops a command whose score is exactly 0); replay + `pop ebp / ret 8`.
     AoWTCPCK
       RP  0x41DCF0  CalculateRangedPath - CHAINED in front of Blood Boil's rp cave: 345 + invalid unit on the hovered
           field -> no path (drop the return, jmp 0x41DFCD) = the click casts nothing; else jmp the previous cave.
       CU  0x41FA1C  UpdateMoveCursor exit - CHAINED: call Blood Boil's cu cave (replays), then 345 + invalid unit
           under the cursor (not the caster itself) -> cursor word [ctl+0x2C] := 0x59 (invalid).
   SOUND: no code needed - for a spell the caster's cast animation (HS action 3, 0x4236E0) is started only on strike 0
   (NextStrike 0x40F3DE: [te+0x14]==0x34 and [te+0x34]!=0 -> skip), the cast-animation sound plays spell cue 0 at its
   frame 0 (0x421D45..0x421DB6) = ONCE per cast; the kind-7 strike effect plays only cue 1 (0x42D3E5, per landing) and,
   for ability 0x41 only, cue 0.  TSFXLibrary.Play (SoundP 0x55406048) looks the cue up by key and returns nil when it
   is missing -> a sound list with cue 0 only is safe: sfx=["SFX\\ZSP\\DUALAD_SUFFOCATE.WAV"] plays one sound per cast.

B) 344 BANSHEE GALE (Winds of Fury clone, kind-0x2F effect per unit) - the kind-0x2F NewFrame plays spell cue 0 TWICE
   per thrown unit (at counter == [fx+0x24] and == [fx+0x28], 0x42BDEB..0x42BE32) and cue 1 at each landing
   (0x42BCF2), on top of the caster's cast-animation cue 0 (strike 0).
       BW  0x42BE07 (`mov eax,[ebp-8] / cmp [eax+0x14],0x34 / jne 0x42BE34`, 9 B) -> jmp cave: spell 344 -> skip the
           per-effect cue 0 (jmp 0x42BE56); else replay.  => cue 0 plays ONCE (the caster's cast animation) = one
           continuous wind+wail like Sandstorm's howl; cue 1 (short landing thud) still plays per unit.
Zones: AoWEPACK 0x55866A00..0x55866C00, AoWTCPCK 0x43F600..0x43F800 (verified zero / reloc-free).  The first 16
bytes of each zone hold the chained sites' PREVIOUS call targets (script-side data, never executed) for --revert.
PIC via call/pop delta where an in-image absolute is read (both DLLs rebase).  Dry-run default; --apply / --revert /
--dis.  Backups <game>\backup\<dll>.bak_airdeathfix.  Must be applied AFTER patch_bloodboil_v1.py (chains its caves);
revert this before reverting Blood Boil.
"""
import argparse, os, shutil, struct, sys
from keystone import Ks, KS_ARCH_X86, KS_MODE_32

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file

SUFF, BANSHEE = 345, 344
UNDEAD_RACE, UNDEAD_ABIL = 0x0B, 0x81
ks = Ks(KS_ARCH_X86, KS_MODE_32)
ANCHOR = bytes.fromhex("e8000000005b81ebffffff7f")
TABLE = 16                                       # zone bytes 0..15: previous targets of the chained sites (data)


def asm_pic(src, va):
    s1 = src.replace("call $D", ".byte 0xe8, 0, 0, 0, 0").replace("sub ebx, $D", "sub ebx, 0x7fffffff")
    b = bytearray(ks.asm(s1, va)[0]); k = 0
    while True:
        k = b.find(ANCHOR, k)
        if k < 0: break
        struct.pack_into("<I", b, k + 8, va + k + 5); k += len(ANCHOR)
    return bytes(b)


# ------------------------------------------------------------------------------------------------ AoWEPACK
EP = dict(dll="AoWEPACK.dll", base=0x55700000, v2f=0x55700C00, zone=(0x55866A00, 0x55866C00))
FINDID, DMG_EXEC, ISCLASS, TCU_CLASSREF = 0x55728C68, 0x55729D14, 0x557010C0, 0x55715A54
# (tag, site, original bytes, cave, kind)  kind: "chain" = the site is a call into a previous cave we sit in front of
EP_HOOKS = [("EX", 0x557F6A2A, None, "ex", "chain"),
            ("AI", 0x557F744F, None, "ai", "chain"),
            ("FC", 0x557F76A5, bytes.fromhex("5f5e5b8be5"), "fc", "jmp")]
EP_VANILLA = {"EX": bytes.fromhex("e8e532f3ff"), "AI": bytes.fromhex("33c0894708")}   # what the sites were before Blood Boil


def ep_caves(prev):
    return [
        # inval(eax = combat object) -> al = 1 if a TCombatUnit whose unit is a machine or undead.  Saves ecx/edx/ebx.
        ("inval", """
            test eax, eax
            jz iv_no0
            push ecx
            push edx
            push ebx
            push eax
            call $D
            pop ebx
            sub ebx, $D
            mov edx, [ebx+%(tcu)#x]
            mov eax, [esp]
            call %(isclass)#x
            test al, al
            jz iv_no
            mov eax, [esp]
            mov eax, [eax+0x4c]
            test eax, eax
            jz iv_no
            mov [esp], eax
            mov edx, [eax]
            call dword ptr [edx+0x114]
            cmp al, 2
            je iv_yes
            mov eax, [esp]
            mov edx, [eax]
            call dword ptr [edx+0xa4]
            cmp al, %(race)d
            je iv_yes
            mov eax, [esp]
            mov edx, %(abil)d
            mov ecx, [eax]
            call dword ptr [ecx+0x148]
            test al, al
            jnz iv_yes
        iv_no:
            xor eax, eax
            jmp iv_out
        iv_yes:
            mov eax, 1
        iv_out:
            add esp, 4
            pop ebx
            pop edx
            pop ecx
            ret
        iv_no0:
            xor eax, eax
            ret
        """),
        # ex: called from TCombatSpellCA.Execute (eax CA, edx combat context) in place of `call TDamageCA.Execute`
        ("ex", """
            cmp dword ptr [eax+0x18], %(suff)d
            je ex_go
            jmp %(prev_ex)#x
        ex_go:
            push ebx
            push esi
            mov ebx, eax
            mov esi, edx
            movzx edx, byte ptr [ebx+0xe]
            mov eax, [esi+0xc]
            call %(findid)#x
            call inval
            test al, al
            jz ex_run
            mov byte ptr [ebx+0x10], 0
        ex_run:
            mov eax, ebx
            mov edx, esi
            pop esi
            pop ebx
            jmp %(dmgexec)#x
        """),
        # ai: GetCombatDamageValueEx (ebx spell, esi target, edi out) - previous cave replays the 5 bytes
        ("ai", """
            call %(prev_ai)#x
            cmp dword ptr [ebx+0x10], %(suff)d
            jne ai_out
            mov eax, esi
            call inval
            test al, al
            jz ai_out
            xor eax, eax
            mov [edi], eax
            mov [edi+4], eax
        ai_out:
            xor eax, eax
            ret
        """),
        # fc: TVaporize fcGetDamageValueEx epilogue (ebx spell, edi target, esi out record)
        ("fc", """
            cmp dword ptr [ebx+0x10], %(suff)d
            jne fc_out
            push eax
            mov eax, edi
            call inval
            test al, al
            pop eax
            jz fc_out
            mov dword ptr [esi], 0
            mov dword ptr [esi+4], 0
        fc_out:
            pop edi
            pop esi
            pop ebx
            mov esp, ebp
            pop ebp
            ret 8
        """),
    ], dict(tcu=TCU_CLASSREF, isclass=ISCLASS, race=UNDEAD_RACE, abil=UNDEAD_ABIL, suff=SUFF, findid=FINDID,
            dmgexec=DMG_EXEC, prev_ex=prev.get("EX", 0), prev_ai=prev.get("AI", 0))


# ------------------------------------------------------------------------------------------------ AoWTCPCK
TC = dict(dll="AoWTCPCK.dll", base=0x400000, v2f=0x400C00, zone=(0x43F600, 0x43F800))
G_GAME, GETMAPLEVEL, GETFIELD, NOPATH = 0x46C064, 0x401E64, 0x401E54, 0x41DFCD
BW_SKIP, BW_ABIL, BW_SPELL = 0x42BE56, 0x42BE34, 0x42BE10
TC_HOOKS = [("RP", 0x41DCF0, None, "rp", "chain"),
            ("CU", 0x41FA1C, None, "cu", "chain"),
            ("BW", 0x42BE07, bytes.fromhex("8b45f8837814347524"), "bw", "jmp")]
TC_VANILLA = {"RP": bytes.fromhex("8b45f483783434"), "CU": bytes.fromhex("c7403400010000")}


def tc_caves(prev):
    return [
        # tcinval(eax = unit HS) -> al = 1 if its unit is a machine or undead.  Saves ecx/edx.
        ("tcinval", """
            test eax, eax
            jz ti_no0
            mov eax, [eax+0x1c]
            test eax, eax
            jz ti_no0
            mov eax, [eax+0x4c]
            test eax, eax
            jz ti_no0
            push ecx
            push edx
            push eax
            mov edx, [eax]
            call dword ptr [edx+0x114]
            cmp al, 2
            je ti_yes
            mov eax, [esp]
            mov edx, [eax]
            call dword ptr [edx+0xa4]
            cmp al, %(race)d
            je ti_yes
            mov eax, [esp]
            mov edx, %(abil)d
            mov ecx, [eax]
            call dword ptr [ecx+0x148]
            test al, al
            jnz ti_yes
            xor eax, eax
            jmp ti_out
        ti_yes:
            mov eax, 1
        ti_out:
            add esp, 4
            pop edx
            pop ecx
            ret
        ti_no0:
            xor eax, eax
            ret
        """),
        # rp: CalculateRangedPath ([ebp-0xC] selected unit HS: +0x34 action, +0x38 spell; [ebp-5]/[ebp-6] hovered x/y)
        ("rp", """
            mov eax, [ebp-0xc]
            cmp dword ptr [eax+0x34], 0x34
            jne rp_prev
            cmp dword ptr [eax+0x38], %(suff)d
            jne rp_prev
            pushal
            call $D
            pop ebx
            sub ebx, $D
            mov eax, [ebx+%(game)#x]
            mov eax, [eax+0x10]
            xor edx, edx
            call %(getmaplevel)#x
            test eax, eax
            jz rp_ok
            movsx edx, byte ptr [ebp-5]
            movsx ecx, byte ptr [ebp-6]
            call %(getfield)#x
            test eax, eax
            jz rp_ok
            mov edx, 0x220104
            mov ecx, [eax]
            call dword ptr [ecx+0x80]
            call tcinval
            test al, al
            jz rp_ok
            popal
            add esp, 4
            jmp %(nopath)#x
        rp_ok:
            popal
        rp_prev:
            jmp %(prev_rp)#x
        """),
        # cu: UpdateMoveCursor exit ([ebp-4] control, [ebp-0x10] selected HS, [ebp-0x14] hovered HS); prev replays
        ("cu", """
            call %(prev_cu)#x
            push eax
            mov eax, [ebp-0x10]
            test eax, eax
            jz cu_out
            cmp dword ptr [eax+0x34], 0x34
            jne cu_out
            cmp dword ptr [eax+0x38], %(suff)d
            jne cu_out
            mov eax, [ebp-0x14]
            test eax, eax
            jz cu_out
            cmp eax, [ebp-0x10]
            je cu_out
            call tcinval
            test al, al
            jz cu_out
            mov eax, [ebp-4]
            mov word ptr [eax+0x2c], 0x59
        cu_out:
            pop eax
            ret
        """),
        # bw: kind-0x2F NewFrame cue-0 block ([ebp-8] effect: +0x14 ability, +0x18 spell id)
        ("bw", """
            mov eax, [ebp-8]
            cmp dword ptr [eax+0x14], 0x34
            jne %(bw_abil)#x
            cmp dword ptr [eax+0x18], %(banshee)d
            je %(bw_skip)#x
            jmp %(bw_spell)#x
        """),
    ], dict(race=UNDEAD_RACE, abil=UNDEAD_ABIL, suff=SUFF, game=G_GAME, getmaplevel=GETMAPLEVEL, getfield=GETFIELD,
            nopath=NOPATH, prev_rp=prev.get("RP", 0), prev_cu=prev.get("CU", 0), bw_abil=BW_ABIL, bw_skip=BW_SKIP,
            bw_spell=BW_SPELL, banshee=BANSHEE)


def build_zone(part, caves_fn, prev, tags):
    """Assemble caves twice (label resolution), local `call/jmp <label>` resolved by name substitution."""
    z0 = part["zone"][0]; base = z0 + TABLE
    caves, fmt = caves_fn(prev)
    where = {name: 0 for name, _ in caves}
    for _ in range(3):
        out = bytearray(); new = {}
        for name, src in caves:
            va = base + len(out); new[name] = va
            s = src % dict(fmt, **{})
            for nm in where: s = s.replace("call %s\n" % nm, "call %#x\n" % where[nm])
            blob = asm_pic(s, va); out += blob
            out += b"\x00" * ((-len(out)) % 16)
        if new == where: break
        where = new
    table = b"".join(struct.pack("<I", prev.get(t, 0)) for t in tags)
    table += b"\x00" * (TABLE - len(table))
    return table + bytes(out), where


def relocs(d, base):
    pe = struct.unpack_from("<I", d, 0x3C)[0]; opt = struct.unpack_from("<H", d, pe + 20)[0]; nsec = struct.unpack_from("<H", d, pe + 6)[0]
    secs = [struct.unpack_from("<IIII", d, pe + 24 + opt + 40 * k + 8) for k in range(nsec)]
    rrva, rsz = struct.unpack_from("<II", d, pe + 24 + 0x88)
    def r2f(rva):
        for vs, va, rs, ro in secs:
            if va <= rva < va + max(vs, rs): return ro + rva - va
    p = r2f(rrva); end = p + rsz; out = set()
    while p < end:
        page, size = struct.unpack_from("<II", d, p)
        if size < 8: break
        for q in range(p + 8, p + size, 2):
            e = struct.unpack_from("<H", d, q)[0]
            if e >> 12 == 3: out.add(base + page + (e & 0xFFF))
        p += size
    return out


def call_target(d, site, v2f):
    b = bytes(d[site - v2f:site - v2f + 5])
    if b[0] not in (0xE8, 0xE9): return None, b[0]
    return site + 5 + struct.unpack_from("<i", b, 1)[0], b[0]


def plan(part, caves_fn, hooks, vanilla):
    path = game_file(part["dll"]); d = bytearray(open(path, "rb").read()); v2f = part["v2f"]; z0, z1 = part["zone"]
    zl = bytes(d[z0 - v2f:z1 - v2f]); chain_tags = [t for t, _, _, _, k in hooks if k == "chain"]
    zone_ours_prev = {t: struct.unpack_from("<I", zl, 4 * i)[0] for i, t in enumerate(chain_tags)} if any(zl) else {}
    states, prev = {}, {}
    # 1st pass: where are the caves going to be (needs prev for the chained ones -> resolve with a provisional build)
    for tag, site, orig, cave, kind in hooks:
        if kind == "chain":
            tgt, op = call_target(d, site, v2f)
            if tgt is None or op != 0xE8: states[tag] = "NOT-A-CALL"; continue
            if z0 <= tgt < z1: states[tag] = "ours"; prev[tag] = zone_ours_prev.get(tag, 0)
            else: states[tag] = "chain-ready"; prev[tag] = tgt
    zone, where = build_zone(part, caves_fn, prev, chain_tags)
    hookb = {}
    for tag, site, orig, cave, kind in hooks:
        n = 5 if kind == "chain" else len(orig)
        h = (b"\xe8" if kind == "chain" else b"\xe9") + struct.pack("<i", where[cave] - (site + 5)) + b"\x90" * (n - 5)
        hookb[tag] = h
        if kind == "jmp":
            live = bytes(d[site - v2f:site - v2f + n])
            states[tag] = "vanilla" if live == orig else "ours" if live == h else "OTHER"
    zstate = "zero" if not any(zl) else "ours" if zl[:len(zone)] == zone and not any(zl[len(zone):]) else "DIFFERS"
    rl = relocs(bytes(d), part["base"])
    bad = [hex(r) for r in rl if z0 - 3 <= r < z1 or any(s - 3 <= r < s + (5 if k == "chain" else len(o)) for _, s, o, _, k in hooks)]
    return dict(path=path, d=d, zone=zone, where=where, zstate=zstate, states=states, hookb=hookb, bad=bad, prev=prev)


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--apply", action="store_true"); ap.add_argument("--revert", action="store_true")
    ap.add_argument("--dis", action="store_true"); a = ap.parse_args()
    parts = [(EP, ep_caves, EP_HOOKS, EP_VANILLA), (TC, tc_caves, TC_HOOKS, TC_VANILLA)]
    plans = []
    for part, caves_fn, hooks, vanilla in parts:
        pl = plan(part, caves_fn, hooks, vanilla); plans.append((part, hooks, pl))
        print("%-13s sites %s | prev %s | zone %s (%d B: %s) | relocs %s" % (
            part["dll"], pl["states"], {k: hex(v) for k, v in pl["prev"].items()}, pl["zstate"], len(pl["zone"]),
            ", ".join("%s @%#x" % kv for kv in pl["where"].items()), pl["bad"] or "none"))
        if a.dis:
            import capstone
            z0 = part["zone"][0]
            for i in capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32).disasm(pl["zone"][TABLE:], z0 + TABLE):
                print("   %08X  %-18s %s %s" % (i.address, i.bytes.hex(), i.mnemonic, i.op_str))
    for _, _, pl in plans:
        if pl["bad"] or any(s in ("OTHER", "NOT-A-CALL") for s in pl["states"].values()): print("ABORT (site/reloc)"); return 1
        if any(v == 0 for v in pl["prev"].values()): print("ABORT (a chained site's previous target is unknown)"); return 1
        ours = any(s == "ours" for s in pl["states"].values())
        if pl["zstate"] == "DIFFERS" and not ours: print("ABORT (zone not free)"); return 1
        if ours and any(s == "chain-ready" for s in pl["states"].values()) and pl["zstate"] != "zero":
            print("ABORT (mixed state: another script chained in front of one of our sites)"); return 1
    outs = []
    for part, hooks, pl in plans:
        d = bytearray(pl["d"]); v2f = part["v2f"]; z0, z1 = part["zone"]
        if a.revert:
            for tag, site, orig, _, kind in hooks:
                if pl["states"][tag] != "ours": continue
                if kind == "chain": d[site - v2f:site - v2f + 5] = b"\xe8" + struct.pack("<i", pl["prev"][tag] - (site + 5))
                else: d[site - v2f:site - v2f + len(orig)] = orig
            d[z0 - v2f:z1 - v2f] = bytes(z1 - z0)
        else:
            d[z0 - v2f:z1 - v2f] = bytes(z1 - z0); d[z0 - v2f:z0 - v2f + len(pl["zone"])] = pl["zone"]
            for tag, site, orig, _, kind in hooks:
                h = pl["hookb"][tag]; d[site - v2f:site - v2f + len(h)] = h
        outs.append((pl["path"], pl["d"], bytes(d)))
    if all(o == n for _, o, n in outs): print("already %s" % ("reverted" if a.revert else "applied")); return 0
    if not (a.apply or a.revert): print("Dry run OK - rerun with --apply (or --revert)."); return 0
    for path, old, new in outs:
        if old == new: continue
        bak = bak_path(path, ".bak_airdeathfix")
        if not os.path.exists(bak): shutil.copy2(path, bak); print("backup ->", bak)
        with open(path, "r+b") as f: f.write(new)
        assert open(path, "rb").read() == new; print("written", path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
