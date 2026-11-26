#!/usr/bin/env python3
r"""
Faceted rock painter (2026-10-31) - shared by the Great Eagle's Nest map sprite (eagle_nest_art_v3) and side
portrait (eagle_nest_side_v5).

Vanilla AoW rock is painted in crisp PLANES (each facet one value, lit from the upper left, dark crevices between
them, bright top surfaces) - not noise.  facet_rock() reproduces that on any silhouette mask:
  * anisotropic Voronoi cells (tall = cliff columns) seeded inside the mask's bounding box;
  * every cell gets a normal = the silhouette's local outward direction (left half faces left, right half faces
    right) + a random tilt -> flat diffuse shading per cell + a slight top-to-bottom darkening inside the cell;
  * crevices where the two nearest seeds are almost equidistant, a thin light lip on the lit side of each crevice;
  * surfaces facing up (sky directly above within `top_px`) get the top-plane colour.
"""
import math

import numpy as np


def _nearest2(px, py, sx, sy, aspect):
    """distances to the nearest / second-nearest seed (anisotropic: dy scaled by aspect) + nearest index"""
    n = len(px)
    d1 = np.full(n, np.inf); d2 = np.full(n, np.inf); i1 = np.zeros(n, int)
    for k in range(len(sx)):
        d = np.hypot(px - sx[k], (py - sy[k]) * aspect)
        m = d < d1
        d2 = np.where(m, d1, np.minimum(d2, d))
        i1 = np.where(m, k, i1)
        d1 = np.where(m, d, d1)
    return d1, d2, i1


def facet_rock(mask, rng, cell, lit_col, shade_col, top_col, crevice_col, aspect=0.45, tilt=0.45,
               light=(-0.62, -0.42, 0.66), crevice_px=None, top_px=None, ambient=0.18, crev_frac=1.0):
    h, w = mask.shape
    ys, xs = np.nonzero(mask)
    if len(xs) == 0:
        return np.zeros((h, w, 3))
    crevice_px = crevice_px or max(1.0, cell * 0.07)
    top_px = top_px or max(2, int(cell * 0.18))
    x0, x1, y0, y1 = xs.min(), xs.max(), ys.min(), ys.max()
    nseed = int((x1 - x0 + cell) * (y1 - y0 + cell) * aspect / (cell * cell)) + 4
    sx = rng.uniform(x0 - cell / 2, x1 + cell / 2, nseed)
    sy = rng.uniform(y0 - cell / 2, y1 + cell / 2, nseed)
    d1, d2, idx = _nearest2(xs.astype(float), ys.astype(float), sx, sy, aspect)
    # silhouette centre line / half width per row -> outward direction
    cl = np.zeros(h); hw = np.ones(h)
    for y in range(y0, y1 + 1):
        r = np.nonzero(mask[y])[0]
        if len(r):
            cl[y] = (r.min() + r.max()) / 2; hw[y] = max(1.0, (r.max() - r.min()) / 2)
    L = np.array(light, float); L /= np.linalg.norm(L)
    # per-cell normal from its seed position
    syc = np.clip(sy.astype(int), y0, y1)
    out_x = np.clip((sx - cl[syc]) / hw[syc], -1.2, 1.2)
    nx = out_x * 1.15 + rng.normal(0, tilt, nseed)
    ny = -0.05 + rng.normal(0, tilt * 0.7, nseed)
    nz = np.sqrt(np.clip(1 - np.clip(nx * nx + ny * ny, 0, 0.95), 0.05, 1))
    nrm = np.stack([nx, ny, nz], 1); nrm /= np.linalg.norm(nrm, axis=1, keepdims=True)
    diff = np.clip(nrm @ L, 0, 1)
    v = diff[idx]
    v = v - 0.12 * np.clip((ys - sy[idx]) / (cell / aspect), -1, 1)        # darker toward the bottom of a facet
    v = np.clip(ambient + (1 - ambient) * v, 0, 1)
    col = np.asarray(shade_col, float)[None] + (np.asarray(lit_col, float) - np.asarray(shade_col, float))[None] * v[:, None]
    # crevices + light lip
    gap = d2 - d1
    crev = np.clip(1 - gap / crevice_px, 0, 1)
    crev = crev * (rng.random(nseed) < crev_frac)[idx]                      # only some facet edges are cracks
    col = col + (np.asarray(crevice_col, float)[None] - col) * (crev * 0.85)[:, None]
    lip = np.clip(1 - np.abs(gap - crevice_px * 1.8) / crevice_px, 0, 1) * (v > 0.55)
    col = col + (255 - col) * (lip * 0.18)[:, None]
    img = np.zeros((h, w, 3))
    img[ys, xs] = col
    # top-facing surfaces
    up = np.zeros_like(mask)
    for k in range(1, top_px + 1):
        up |= ~np.roll(mask, k, 0)
    up &= mask
    up[:top_px] &= mask[:top_px]
    tv = np.clip(0.75 + 0.25 * diff[idx], 0, 1)
    tm = up[ys, xs]
    tcol = np.asarray(top_col, float)[None] * tv[:, None]
    img[ys[tm], xs[tm]] = tcol[tm]
    return img
