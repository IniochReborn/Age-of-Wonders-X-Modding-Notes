"""Shared backup-path convention for the patch scripts (2026-09-17).

Backups live in a `backup\\` folder inside the game directory, mirroring the
target's path relative to that directory, so the game folder stays clean:

    <game>\\AoWEPACK.dll            -> <game>\\backup\\AoWEPACK.dll.bak_healai
    <game>\\Dict\\Release.mld       -> <game>\\backup\\Dict\\Release.mld.bak_frost

`bak_path(target, suffix)` returns that path (creating the folder on demand).
For reading (revert / "already applied" checks) it falls back to the legacy
location beside the target if the backup folder copy does not exist, so old
backups that were never moved still revert.

Usage in a script:
    from bakpath import bak_path
    BAK = bak_path(DLL, ".bak_feature")
"""
import os

BACKUP_DIR = "backup"

# Game-dir markers: the backup folder is created in the nearest ancestor that
# holds the game executable, so a target in Dict\\ or Release\\ lands in
# <game>\\backup\\Dict\\... rather than <game>\\Dict\\backup\\...
_MARKERS = ("AoWx.exe", "AoWEPACK.dll", "AoWSetup.exe")


def game_dir_of(target):
    d = os.path.dirname(os.path.abspath(target))
    probe = d
    for _ in range(4):
        if any(os.path.exists(os.path.join(probe, m)) for m in _MARKERS):
            return probe
        parent = os.path.dirname(probe)
        if parent == probe:
            break
        probe = parent
    return d


def bak_path(target, suffix, create=True):
    """Backup path for `target` with the given `.bak_xxx` suffix."""
    target = os.path.abspath(target)
    game = game_dir_of(target)
    rel = os.path.relpath(target, game)
    new = os.path.join(game, BACKUP_DIR, rel + suffix)
    legacy = target + suffix
    if not os.path.exists(new) and os.path.exists(legacy):
        return legacy
    if create:
        os.makedirs(os.path.dirname(new), exist_ok=True)
    return new


def game_dir():
    """The game folder (2026-09-20): AOW_GAME_DIR if set and present, else the
    parent of this `patch scripts` folder (the project folder IS the game dir).
    Never bake an absolute machine path into a script."""
    d = os.environ.get("AOW_GAME_DIR")
    if d and os.path.isdir(d):
        return d
    return os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))


def game_file(*parts):
    """Path of a file inside the game folder: game_file("Release", "Spells.pfs")."""
    return os.path.join(game_dir(), *parts)
