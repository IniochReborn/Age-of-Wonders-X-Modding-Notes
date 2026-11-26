"""diag_veh_attach.py + on every access violation also dump memory around eax/ebx/ecx/edx/esi
(object fields, VMT candidates, palette-grid fields).  Usage: python diag_veh_attach_dump.py <pid>
Output: veh_attach_dump.txt next to this script."""
import os, struct, sys, time
import diag_veh_logger as L
import diag_veh_attach as A

L.OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "veh_attach_dump.txt")
_log = L.log
_hp = [None]
_orig_open = L.k32.OpenProcess


def open_wrap(acc, inh, pid):
    h = _orig_open(acc, inh, pid); _hp[0] = h; return h


L.k32.OpenProcess = open_wrap
A.k32.OpenProcess = open_wrap


def log(s):
    _log(s)
    if "esp=" in s and "eax=" in s and _hp[0]:
        regs = dict(p.split("=") for p in s.split() if "=" in p)
        for r in ("eax", "ebx", "ecx", "edx", "esi"):
            v = int(regs[r], 16)
            if v > 0x10000:
                d = L.rpm(_hp[0], v - 0x10, 0x60)
                if d:
                    _log("    [%s-0x10] %s" % (r, d.hex()))
        v = int(regs["ebx"], 16)
        d = L.rpm(_hp[0], v + 0x230, 0x50)
        if d:
            _log("    [ebx+0x230] %s" % d.hex())


L.log = log
if __name__ == "__main__":
    A.main()
