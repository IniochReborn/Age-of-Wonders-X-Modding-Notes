"""
aowxlib.presets - image parameter presets for new ILB images.

Two mechanisms, in order of preference:

  match_library()  - inherit the dominant parameter set of the library being
                     edited. Measured over the retail data: 74.5% of the 689
                     game ILBs use exactly ONE parameter set for every image
                     and 85% are >=90% dominant, so this is almost always the
                     correct answer, and it beats a global preset where
                     libraries legitimately differ (retail face libraries use
                     bmAlpha, the AoWx-added ones use bmUser).

  PRESETS          - named starting points for a library built from scratch,
                     mined from the retail data.
"""
from __future__ import annotations
import collections
from . import ilb

# Mined from 689 retail ILBs / 33k images. Each entry gives the exact record
# fields plus the canonical canvas size for that kind of art.
PRESETS = {
    "unit_sprite": {
        "label": "Unit sprite (animation frames)",
        "canvas": (64, 64), "depth": "8-bit indexed",
        "fields": {"type": 2, "info": 2, "loadMode": 1, "clip_x": 0},
        "note": "81% of the 21,263 images in Images\\UNITS. 6 rows of facings.",
    },
    "portrait_face": {
        "label": "Portrait / face",
        "canvas": (103, 128), "depth": "16-bit RGB565",
        "fields": {"type": 16, "info": 3, "loadMode": 1, "drawMode": 0x0000, "blendValue": 0},
        "note": "Retail faces use bmAlpha (0x0100); AoWx-added ones use bmUser (0x0000).",
    },
    "item_icon": {
        "label": "Item icon",
        "canvas": (41, 42), "depth": "16-bit RGB565",
        "fields": {"type": 17, "info": 3, "loadMode": 1, "drawMode": 0x0100,
                   "blendValue": 0, "clip_x": 0},
    },
    "structure_map": {
        "label": "Structure / map object",
        "canvas": (56, 63), "depth": "16-bit RGB565",
        "fields": {"type": 17, "info": 3, "loadMode": 1, "drawMode": 0x0100,
                   "blendValue": 0, "clip_x": 0x466214},
    },
    "tactical_combat": {
        "label": "Tactical-combat object",
        "canvas": (64, 64), "depth": "16-bit RGB565",
        "fields": {"type": 17, "info": 3, "loadMode": 1, "drawMode": 0x0100,
                   "blendValue": 0, "clip_x": 0x465EEC},
    },
    "spell_effect": {
        "label": "Spell / magic effect",
        "canvas": (64, 64), "depth": "16-bit RGB565",
        "fields": {"type": 22, "info": 3, "loadMode": 1, "drawMode": 0x0302,
                   "blendValue": 80},
        "note": "smBlended + bmIntensity, the washout look used by Images\\Effects.",
    },
    "race_set": {
        "label": "Race set (flags, banners, city)",
        "canvas": (64, 64), "depth": "8-bit indexed",
        "fields": {"type": 2, "info": 3, "loadMode": 1, "clip_x": 0},
    },
    "mountain": {
        "label": "Mountain",
        "canvas": (60, 50), "depth": "16-bit RGB565",
        "fields": {"type": 17, "info": 3, "loadMode": 1, "drawMode": 0x0100,
                   "blendValue": 0, "clip_x": 0x466214},
    },
    "scene_backdrop": {
        "label": "Scene backdrop",
        "canvas": (272, 372), "depth": "16-bit RGB565",
        "fields": {"type": 16, "info": 3, "loadMode": 1, "drawMode": 0x0100, "blendValue": 0},
    },
    "ui_element": {
        "label": "UI element",
        "canvas": (0, 0), "depth": "8-bit indexed",
        "fields": {"type": 2, "info": 3, "loadMode": 1, "clip_x": 0},
    },
}

# fields copied when inheriting from a library or another image
INHERITED = ("type", "info", "loadMode", "drawMode", "blendValue", "clip_x", "pal", "transp")


def _signature(rec):
    return (rec.get("type"), rec.get("info"), rec.get("loadMode"),
            rec.get("drawMode"), rec.get("blendValue"), rec.get("clip_x", 0))


def library_profile(lib):
    """Return (dominant_signature, share, distinct_count, total) for a library."""
    c = collections.Counter()
    for _img, rec in lib.all_records():
        if rec.blank:
            continue
        c[_signature(rec)] += 1
    if not c:
        return None, 0.0, 0, 0
    sig, n = c.most_common(1)[0]
    total = sum(c.values())
    return sig, n / total, len(c), total


def dominant_record(lib):
    """The most representative existing record, to inherit settings from."""
    sig, _share, _n, _tot = library_profile(lib)
    if sig is None:
        return None
    for _img, rec in lib.all_records():
        if not rec.blank and _signature(rec) == sig:
            return rec
    return None


def match_library(lib, name="new.bmp"):
    """Build a new record inheriting the library's dominant parameter set."""
    src = dominant_record(lib)
    if src is None:
        return apply_preset("item_icon", name)
    rec = ilb.new_record(src["type"], name, src.get("info", 3))
    for k in INHERITED:
        if k in src:
            rec[k] = src[k]
    rec["name"] = name
    rec["sub"] = 0
    return rec


def apply_preset(key, name="new.bmp"):
    p = PRESETS[key]
    f = p["fields"]
    rec = ilb.new_record(f["type"], name, f.get("info", 3))
    for k, v in f.items():
        if k != "type":
            rec[k] = v
    return rec


def copy_settings(src, dst):
    """Copy the parameter set of one record onto another (keeps pixels/name)."""
    for k in INHERITED:
        if k in src:
            dst[k] = src[k]
    dst["info"] = src.get("info", dst.get("info", 3))
    return dst


def outliers(lib):
    """Records whose settings differ from the library's dominant set."""
    sig, _share, distinct, _tot = library_profile(lib)
    if sig is None or distinct <= 1:
        return []
    out = []
    for img, rec in lib.all_records():
        if not rec.blank and _signature(rec) != sig:
            out.append((img, rec))
    return out
