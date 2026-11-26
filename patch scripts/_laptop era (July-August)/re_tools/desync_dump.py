#!/usr/bin/env python3
"""Dump the LAN-desync diagnostic buffers from running AoWx.exe processes.

Pairs with build_scripts/build_desync_diag.py.  Run AFTER reproducing the
out-of-sync error (both game instances must still be running - the OutOfSync
dialog keeps the process alive).  With two instances found, prints each
process's negotiate breadcrumbs + synced-RNG ring timeline and diffs the
rings to find the first divergent synced Random call.

Layout (preferred-base VAs; RVA = VA - 0x55700000):
  SCRATCH 0x558FA980: see build_desync_diag.py docstring
  RING    0x558FAA00: +0 dd count, +8: 128 x {caller/tag dd, seed/extra dd}
Marker tags in the ring: NEGO/OFFR/SELE/AMNT/JOIN (recruit-flow milestones).
"""
import ctypes
import ctypes.wintypes as wt
import os
import sys

SCRATCH_RVA = 0x1FA980
RING_RVA    = 0x1FAA00
RING_N      = 128
GBRING_RVA  = 0x1FAE20          # build_desync_getbusy.py: GetBusy/GetLocal ring
GBRING_N    = 64
PREF_BASE   = 0x55700000

PROCESS_QUERY_INFORMATION = 0x0400
PROCESS_VM_READ = 0x0010
LIST_MODULES_32BIT = 0x01

k32 = ctypes.windll.kernel32
psapi = ctypes.windll.psapi

TAG_NEGO, TAG_OFFR, TAG_SELE, TAG_AMNT, TAG_JOIN = (
    0x4E45474F, 0x4F464652, 0x53454C45, 0x414D4E54, 0x4A4F494E)
TAG_MOVE, TAG_SYNC, TAG_BOOM = 0x4D4F5645, 0x53594E43, 0x424F4F4D
TAG_CAPT, TAG_RELS, TAG_AIUL, TAG_WORK, TAG_CREA, TAG_CRE2 = (
    0x43415054, 0x52454C53, 0x4149554C, 0x574F524B, 0x43524541, 0x43524532)
TAG_ANIM, TAG_ELOG, TAG_STAT = 0x414E494D, 0x454C4F47, 0x53544154
TAG_CRE3, TAG_CRE4, TAG_CRE5 = 0x43524533, 0x43524534, 0x43524535
TAGS = {TAG_NEGO: 'NEGO', TAG_OFFR: 'OFFR', TAG_SELE: 'SELE',
        TAG_AMNT: 'AMNT', TAG_JOIN: 'JOIN',
        TAG_MOVE: 'MOVE', TAG_SYNC: 'SYNC', TAG_BOOM: 'BOOM',
        TAG_CAPT: 'CAPT', TAG_RELS: 'RELS', TAG_AIUL: 'AIUL',
        TAG_WORK: 'WORK', TAG_CREA: 'CREA', TAG_CRE2: 'CRE2',
        TAG_CRE3: 'CRE3', TAG_CRE4: 'CRE4', TAG_CRE5: 'CRE5',
        TAG_ANIM: 'ANIM', TAG_ELOG: 'ELOG', TAG_STAT: 'STAT'}


def find_pids():
    import subprocess
    out = subprocess.check_output(
        ["tasklist", "/FI", "IMAGENAME eq AoWx.exe", "/FO", "CSV", "/NH"],
        text=True)
    pids = []
    for line in out.splitlines():
        parts = [p.strip('"') for p in line.split('","')]
        if len(parts) >= 2 and parts[0].lower() == "aowx.exe":
            pids.append(int(parts[1]))
    return pids


def module_base(h, want=b"aowepack.dll"):
    mods = (wt.HMODULE * 1024)()
    needed = wt.DWORD()
    if not psapi.EnumProcessModulesEx(h, mods, ctypes.sizeof(mods),
                                      ctypes.byref(needed), LIST_MODULES_32BIT):
        return None
    buf = ctypes.create_string_buffer(260)
    for i in range(needed.value // ctypes.sizeof(wt.HMODULE)):
        psapi.GetModuleBaseNameA(h, mods[i], buf, 260)
        if buf.value.lower() == want:
            return mods[i]
    return None


def read_mem(h, addr, n):
    buf = ctypes.create_string_buffer(n)
    got = ctypes.c_size_t()
    if not k32.ReadProcessMemory(h, ctypes.c_void_p(addr), buf, n,
                                 ctypes.byref(got)):
        return None
    return buf.raw


def load_symbols():
    """caller VA -> nearest AoWEPACK export at or below it."""
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from pescan import PE
        game = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
            os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))
        pe = PE(os.path.join(game, "AoWEPACK.dll"))
        syms = sorted((PREF_BASE + rva, name) for name, rva in pe.exports())
        return syms
    except Exception as e:
        print("(symbol load failed: %s)" % e)
        return []


def sym_for(syms, va):
    import bisect
    if not syms:
        return "0x%08X" % va
    i = bisect.bisect_right([s[0] for s in syms], va) - 1
    if i < 0:
        return "0x%08X" % va
    base, name = syms[i]
    off = va - base
    name = name.replace('@23EDC2EF', '').replace('AoWE.', '')
    if off > 0x2000:
        return "0x%08X" % va
    return "%s+0x%X" % (name, off) if off else name


class Proc:
    def __init__(self, pid):
        self.pid = pid
        self.h = k32.OpenProcess(
            PROCESS_QUERY_INFORMATION | PROCESS_VM_READ, False, pid)
        self.base = module_base(self.h) if self.h else None
        self.delta = (self.base - PREF_BASE) if self.base else 0
        self.netbase = module_base(self.h, b"network.dpl") if self.h else None

    def netring(self):
        """diag7: Network.dpl BSS mini-ring @RVA 0x8100 (send-cand/recv)."""
        if not self.netbase:
            return 0, []
        d = read_mem(self.h, self.netbase + 0x8100, 4 + 32 * 4)
        if not d:
            return 0, []
        count = int.from_bytes(d[0:4], 'little')
        out = []
        for n in range(max(0, count - 32), count):
            i = n & 31
            e = int.from_bytes(d[4 + i*4: 8 + i*4], 'little')
            out.append((n, e))
        return count, out

    def scratch(self):
        return read_mem(self.h, self.base + SCRATCH_RVA, 0x2C)

    def ring(self):
        d = read_mem(self.h, self.base + RING_RVA, 8 + RING_N * 8)
        if not d:
            return 0, []
        count = int.from_bytes(d[0:4], 'little')
        entries = []
        for n in range(max(0, count - RING_N), count):
            i = n & (RING_N - 1)
            caller = int.from_bytes(d[8 + i*8: 12 + i*8], 'little')
            val = int.from_bytes(d[12 + i*8: 16 + i*8], 'little')
            entries.append((n, caller, val))
        return count, entries

    def gbring(self):
        d = read_mem(self.h, self.base + GBRING_RVA, 4 + GBRING_N * 4)
        if not d:
            return 0, []
        count = int.from_bytes(d[0:4], 'little')
        out = []
        for n in range(max(0, count - GBRING_N), count):
            i = n & (GBRING_N - 1)
            e = int.from_bytes(d[4 + i*4: 8 + i*4], 'little')
            out.append((n, e & 0xFF, (e >> 8) & 0xFF, (e >> 16) & 0xFF))  # idx,busy,local
        return count, out


def dump_scratch(d):
    if not d:
        print("  (scratch read failed)")
        return
    dw = lambda o: int.from_bytes(d[o:o+4], 'little')
    print("  NegotiateTE.Execute count : %d" % dw(0))
    print("    last TE: player=%d xyl=(%d,%d,%d) paid=%d accept=%d flags=0x%02X mode=%d"
          % (d[4], d[5], d[6], d[7], dw(8), d[0x0C], d[0x0D], d[0x0E]))
    print("  Offer reached count       : %d  (Validate passed)" % dw(0x10))
    print("    last offer: paid=%d mode=%d accept=%d flags=0x%02X player=%d"
          % (dw(0x14), d[0x18], d[0x19], d[0x1A], d[0x1B]))
    print("  GetJoinSelection (last)   : 0x%02X" % d[0x1C])
    print("  JoinAmount (last)         : %d" % dw(0x20))
    print("  join-done count           : %d" % dw(0x24))
    print("  amount-bail count         : %d  (silent no-join!)" % dw(0x28))


def fmt_entry(syms, delta, n, caller, val):
    if caller == TAG_MOVE:
        return "#%-5d [MOVE] first-hex=(%d,%d,%d)" % (n, val & 0xFF,
                                                      (val >> 8) & 0xFF, (val >> 16) & 0xFF)
    if caller in (TAG_SYNC, TAG_BOOM):
        return "#%-5d [%s] seed=%08X%s" % (n, TAGS[caller], val,
                                           "  <<< OUT OF SYNC FIRED" if caller == TAG_BOOM else "")
    if caller in (TAG_CAPT, TAG_RELS):
        return "#%-5d [%s] tok#=%d timemode=%d%s" % (
            n, TAGS[caller], val & 0xFFFFFF, val >> 24,
            "  <-- REALTIME (nondeterministic)" if (val >> 24) == 1 else "")
    if caller == TAG_AIUL:
        return "#%-5d [AIUL] tok#=%d lockdepth-pre=%d" % (
            n, val & 0xFFFFFF, val >> 24)
    if caller == TAG_WORK:
        return "#%-5d [WORK] player=%d did-work=%d" % (
            n, (val >> 8) & 0xFF, val & 0xFF)
    if caller == TAG_CREA:
        return "#%-5d [CREA] first-hex=(%d,%d,%d) setup-ok=%d" % (
            n, val & 0xFF, (val >> 8) & 0xFF, (val >> 16) & 0xFF, val >> 24)
    if caller == TAG_CRE2:
        return "#%-5d [CRE2] created-by %s" % (n, sym_for(syms, val - delta))
    if caller == TAG_CRE3:
        return "#%-5d [CRE3] MoveArmyEx called from %s" % (n, sym_for(syms, val - delta))
    if caller == TAG_CRE4:
        return ("#%-5d [CRE4] grandparent(if via MoveArmy wrapper)= %s"
                % (n, sym_for(syms, val - delta)))
    if caller == TAG_CRE5:
        return "#%-5d [CRE5] ExecuteMove invoked by %s" % (n, sym_for(syms, val - delta))
    if caller == TAG_ANIM:
        return "#%-5d [ANIM] owner=%d dest=(%d,%d,%d)  <-- animation started" % (
            n, val >> 24, val & 0xFF, (val >> 8) & 0xFF, (val >> 16) & 0xFF)
    if caller == TAG_ELOG:
        return "#%-5d [ELOG] delay %d->%d cbcount=%d" % (
            n, (val >> 8) & 0xFF, val & 0xFF, (val >> 16) & 0xFF)
    if caller == TAG_STAT:
        return ("#%-5d [STAT] player=%d busy48=%d%s%s%s cbq=%d elogdelay=%d"
                % (n, val >> 24, val & 0xFF,
                   " NOPLAYER" if val & 0x8000 else "",
                   " COMBAT" if val & 0x100 else "",
                   " p44" if val & 0x200 else "",
                   (val >> 10) & 0xF, (val >> 16) & 0xFF))
    if caller in TAGS:
        return "#%-5d [%s] extra=%d" % (n, TAGS[caller], val)
    return "#%-5d %-46s seed=%08X" % (n, sym_for(syms, caller - delta), val)


def main():
    pids = find_pids()
    if not pids:
        print("No AoWx.exe running.")
        return 1
    syms = load_symbols()
    procs = []
    for pid in pids:
        p = Proc(pid)
        if not p.base:
            print("pid %d: AoWEPACK.dll not found, skipping" % pid)
            continue
        procs.append(p)

    rings = {}
    for p in procs:
        print("\n===== AoWx.exe pid %d (AoWEPACK base 0x%X, delta %+#x) ====="
              % (p.pid, p.base, p.delta))
        sc = p.scratch()
        if sc and any(sc):
            dump_scratch(sc)             # v1 negotiate breadcrumbs, if present
        count, entries = p.ring()
        rings[p.pid] = (count, entries)
        print("  RNG ring: %d total entries, showing last %d:" % (count, len(entries)))
        for n, caller, val in entries[-48:]:
            print("   ", fmt_entry(syms, p.delta, n, caller, val))
        nc, ne = p.netring()
        if nc:
            print("  NET ring (diag7): %d total  [send-cand: player|batch-count;"
                  " RECV: src player]:" % nc)
            for n, e in ne:
                if e & 0x80000000:
                    print("    #%-4d RECV  src-player=%d" % (n, e & 0xFF))
                else:
                    print("    #%-4d send-cand player=%d batch=%d"
                          % (n, e & 0xFF, (e >> 8) & 0xFFFF))
        gc, gb = p.gbring()
        if gc:
            print("  GetBusy ring: %d total checks in AI auto-produce loop"
                  " (player idx : busy / local):" % gc)
            for n, idx, busy, local in gb[-24:]:
                print("    #%-5d player=%-2d busy=%d local=%d%s"
                      % (n, idx, busy, local,
                         "   <-- busy&local BOTH set" if busy and local else
                         ("   <-- not busy (loop continues, draws RNG)" if not busy else "")))

    if len(procs) == 2:
        a, b = procs
        ca, ea = rings[a.pid]
        cb, eb = rings[b.pid]
        # comparable key per entry: caller normalized to preferred base (or tag);
        # SEED VALUES are NOT compared - the synced RNG is one deterministic chain,
        # so values always match when draw-counts match; only the CALLER SEQUENCE
        # (who consumed each draw) reveals a real lockstep divergence.
        def kcaller(p, c):
            return c if c in TAGS else c - p.delta
        seqa = [kcaller(a, c) for _, c, _ in ea]
        seqb = [kcaller(b, c) for _, c, _ in eb]

        print("\n===== RING DIFF (pid %d vs pid %d) =====" % (a.pid, b.pid))
        print("total ring entries since launch: %d vs %d  (absolute counts"
              " differ by pre-game/local activity - aligning by content)"
              % (ca, cb))

        # shift that maximizes identical aligned callers: seqa[i] <-> seqb[i-shift]
        best_len, shift = -1, 0
        for s in range(-len(seqb) + 1, len(seqa)):
            lo, hi = max(0, s), min(len(seqa), len(seqb) + s)
            if hi - lo < 8:
                continue
            m = sum(1 for i in range(lo, hi) if seqa[i] == seqb[i - s])
            if m > best_len:
                best_len, shift = m, s
        lo, hi = max(0, shift), min(len(seqa), len(seqb) + shift)
        print("best alignment: shift %+d, %d/%d aligned entries with identical"
              " callers" % (shift, best_len, hi - lo))

        firstdiff = next((i for i in range(lo, hi) if seqa[i] != seqb[i - shift]),
                         None)
        if firstdiff is None:
            print("aligned overlap fully identical; divergence is in the tails:")
            firstdiff = hi
        else:
            print("\nFIRST CALLER SPLIT in the aligned timeline:")
        for i in range(max(lo, firstdiff - 8), min(len(seqa), firstdiff + 6)):
            mark = "  <<< SPLIT" if i == firstdiff else ""
            n1, c1, v1 = ea[i]
            print("  A:", fmt_entry(syms, a.delta, n1, c1, v1), mark)
            j = i - shift
            if 0 <= j < len(eb):
                n2, c2, v2 = eb[j]
                print("  B:", fmt_entry(syms, b.delta, n2, c2, v2))
            else:
                print("  B:  (stream ended)")
        for j in range(max(0, len(seqa) - shift), len(seqb)):
            n2, c2, v2 = eb[j]
            print("  B+:", fmt_entry(syms, b.delta, n2, c2, v2), " (B-only tail)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
