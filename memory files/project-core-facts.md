---
name: project-core-facts
description: AoWx core facts - which binaries are live (.dll vs .dpl), VA-to-file math per module, install history, next free code caves, always-rules
metadata:
  type: project
---

AoWx — community mod for Age of Wonders (1999, Delphi). No source; everything is binary patching of AoWx.exe, AoWEPACK.dll, AoWTCPCK.dll, HSEPack.dpl, aowInt.dpl, VCL30.dpl, and **AoWDevX.exe** (editor; renamed from AoWDevEd.exe 7/21).
**DLL vs DPL**: .dll = modded/live, .dpl = original — except HSEPack/aowInt/VCL30/Dcpack .dpl are live (no .dll twin).
**VA math**: AoWEPACK.dll = file+0x55700C00 · AoWTCPCK.dll & AoWx.exe = file+0x400C00 · HSEPack.dpl = file+0x55600C00 · aowInt.dpl CODE = file+0x59800C00 (DATA = file+0x59801A00!) · VCL30.dpl = file+0x41300C00 · Dcpack.dpl = file+0x55100C00.
**🏠 10/11 INSTALLED the laptop's Oct-11 delta into the project root** (dual-sphere Death/Fire spells, High Prayer glow, AoO vcall soft-lock fix, SpellTypes relocation → 0x43C000; see [[transfer-home-2026-10-11]]). Overwritten files saved in `backup\pre_oct11\`. Laptop STALE after 10/11.
**🏠 9/20 INSTALLED laptop 410 work INTO THE PROJECT ROOT** (user: no 410 subfolder — the project folder stays the game dir; 410 binaries/data/backups merged over it, AOW_GAME_DIR = project root; laptop backups now in `backup\` via `patch scripts\bakpath.py`). The 31 laptop scripts had BAKED laptop paths (`C:\Users\<user>\...\410 prerelease`) — rewritten 9/20 to `bakpath.game_dir()/game_file()` (AOW_GAME_DIR or parent of patch scripts); all dry-run as ALREADY PATCHED. Home python is `py -3.10`. See [[transfer-home-2026-09-20]] + [[aowx-410-pending-tests]].
**Next free caves** (full history in [next-free-caves.md](next-free-caves.md)): AoWEPACK ⚠ index STALE (0x55864300 taken by drought) — scan script range claims; 0x55833100+ free 10/21 · AoWTCPCK **0x43E820** (to 0x43E900; 0x43B100–0x43C000 + 0x43C240–0x43C400 also free; Implosion v2 zone B 0x43E000–0x43E16D; alias zone now 0x43AD00–0x43AF00; SpellTypes table 0x43C000–0x43C200) · AoWx.exe `.xbfs` FULL → `.xtut` FULL to 0x639000 (scroll spells took 0x638C00) (CODE full; exe DOES have a .reloc) · aowInt **0x59824700** · VCL30 CODE 0x413A91C0 · AoWDevX section table FULL. **Always**: scan .reloc ([[patching-over-relocs-gotcha]]); PIC delta-trick for in-image addresses ([[rebase-crash-runtime-error-216]]).
**Always**: scan .reloc before overwriting code ([[patching-over-relocs-gotcha]]); PIC delta-trick for in-image addresses ([[rebase-crash-runtime-error-216]]).
