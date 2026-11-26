# -*- coding: utf-8 -*-
"""Generate a batch of random maps: 2 of each size (S/M/L/XL), random seeds,
seed-named outputs in Scenario/Custom. Usage: py "patch scripts/mapgen/gen_batch.py" """
import os, sys, random, subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
GAME = os.path.abspath(os.path.join(HERE, '..', '..'))
os.chdir(GAME)

for sz in ('S', 'S', 'M', 'M', 'L', 'L', 'XL', 'XL'):
    seed = random.randrange(1_000_000)
    r = subprocess.run([sys.executable, os.path.join(HERE, 'generate_map_v4.py'),
                        str(seed), sz], capture_output=True, text=True, cwd=GAME)
    if r.returncode != 0:
        print(f"FAILED {sz} seed {seed}:\n{r.stderr[-500:]}")
        continue
    src = f'Scenario/Custom/xGen6 {sz}.hsm'
    dst = f'Scenario/Custom/xGen6 {sz} (seed {seed}).hsm'
    os.replace(src, dst)
    for line in r.stdout.splitlines()[:3]:
        print(line)
    print(f"   -> {os.path.basename(dst)}")
