#!/usr/bin/env python3
r"""Wait for AoWx.exe (or argv[1]) to run, give it 8 s to finish starting, attach diag_veh_logger (--pid), and repeat
for the next launch (2026-11-14).  Log: veh_log.txt (appended).  Usage: py -3.10 diag_veh_wait_attach.py [exe] [minutes=120]"""
import os, subprocess, sys, time
import psutil

HERE = os.path.dirname(os.path.abspath(__file__))
name = (sys.argv[1] if len(sys.argv) > 1 else "AoWx.exe").lower()
end = time.time() + 60 * (int(sys.argv[2]) if len(sys.argv) > 2 else 120)
while time.time() < end:
    ps = [p for p in psutil.process_iter(["name"]) if (p.info["name"] or "").lower() == name]
    if not ps:
        time.sleep(1); continue
    time.sleep(8)
    if not ps[0].is_running():
        continue
    subprocess.call([sys.executable, os.path.join(HERE, "diag_veh_logger.py"), "--pid", str(ps[0].pid)], cwd=HERE,
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
