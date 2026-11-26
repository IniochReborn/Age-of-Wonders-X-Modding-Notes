#!/usr/bin/env python3
r"""Read the Load/Save/New-Game dialog state out of the RUNNING game (run elevated: the game runs elevated).
Dumps: the --diag counters of patch_loaddlg_date_sort_v1.py (0x60EFF0..), the TFileDlgWindow instance [0x45B104]:
mode (+0x148), and for FileLB (+0x58) / SaveLB (+0xD8) / DateLB (+0xE8) the TAOWListBox items (+0x114) =
TStringList (FList +4 -> array of {PString, Object} pairs, FCount +8): count and the first N entries with the
TDateTime double at [obj+4] when an object is attached.  Output -> loaddlg_probe_log.txt next to this script."""
import ctypes, ctypes.wintypes as wt, os, struct, subprocess, sys, time
k32 = ctypes.windll.kernel32
LOG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "loaddlg_probe_log.txt")
lines = []
def say(*a):
    t = " ".join(str(x) for x in a); print(t); lines.append(t)
def pids(name="AoWx.exe"):
    out = subprocess.check_output(["tasklist", "/FI", f"IMAGENAME eq {name}", "/FO", "CSV", "/NH"], text=True)
    return [int(l.split('","')[1].strip('"')) for l in out.splitlines() if l.lower().startswith('"' + name.lower())]
def rd(h, a, n):
    buf = ctypes.create_string_buffer(n); got = ctypes.c_size_t()
    if not k32.ReadProcessMemory(h, ctypes.c_void_p(a), buf, n, ctypes.byref(got)): return None
    return buf.raw[:got.value]
def u32(h, a):
    b = rd(h, a, 4); return struct.unpack("<I", b)[0] if b else None
def pstr(h, p):
    if not p: return ""
    L = u32(h, p - 4) or 0
    b = rd(h, p, min(L, 80)) or b""; return b.decode("latin1", "replace")
def dump_list(h, name, lb):
    if not lb: say("  %s: listbox nil" % name); return
    items = u32(h, lb + 0x114); say("  %s: listbox %#x items %#x sel %s" % (name, lb, items or 0, u32(h, lb + 0x120)))
    if not items: return
    flist, cnt = u32(h, items + 4), u32(h, items + 8)
    say("    FCount %s FList %#x" % (cnt, flist or 0))
    for i in range(min(cnt or 0, 8)):
        sp, op = u32(h, flist + 8 * i), u32(h, flist + 8 * i + 4)
        dt = struct.unpack("<d", rd(h, op + 4, 8))[0] if op and rd(h, op + 4, 8) else None
        say("    [%d] %-40r obj %#x date %s" % (i, pstr(h, sp), op or 0, dt))
def main():
    ps = pids()
    if not ps: say("AoWx.exe not running"); return
    h = k32.OpenProcess(0x0410, False, ps[0])
    if not h: say("OpenProcess failed (run elevated) err", k32.GetLastError()); return
    say("pid", ps[0], time.strftime("%H:%M:%S"))
    c = rd(h, 0x60EFF0, 16)
    if c: say("diag counters: entries %d last-mode %d datebtn-calls %d last-self %#x" % struct.unpack("<IIII", c))
    dlg = u32(h, 0x45B104); say("dialog [0x45B104] = %#x" % (dlg or 0))
    if dlg:
        say("  VMT %#x mode(+0x148) %s visible(+0x75 of window %#x) %s" % (u32(h, dlg) or 0, u32(h, dlg + 0x148), u32(h, dlg + 0x44) or 0,
            (rd(h, (u32(h, dlg + 0x44) or 0) + 0x75, 1) or b"?")[0] if u32(h, dlg + 0x44) else "?"))
        for name, off in (("FileLB", 0x58), ("SaveLB", 0xD8), ("DateLB", 0xE8)):
            dump_list(h, name, u32(h, dlg + off))
    open(LOG, "w", encoding="utf-8").write("\n".join(lines) + "\n")
if __name__ == "__main__":
    main()
    if sys.stdout.isatty(): input("done - Enter")
