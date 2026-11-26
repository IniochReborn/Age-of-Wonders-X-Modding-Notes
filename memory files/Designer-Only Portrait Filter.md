# Designer-Only Portrait Filter

**One-line:** Restore the vanilla behaviour where hero/leader portraits flagged "Designer Only" / "Reserved" in the editor are hidden from in-game leader customization (AoW+ had disabled this).

**Status:** DONE / confirmed working. Two-byte patch. Backup: `AoWEPACK.dll.bak_predevfix`.

---

## File patched
- **AoWEPACK.dll** — ImageBase `0x55700000`, CODE section raw offset `0x400`, RVA `0x1000` → **VA = file_offset + 0x55700C00**.

## Background / root cause
Our files are AoW+ based. AoW+'s changelog line "Reserved campaign portraits can be selected when creating leaders" was implemented by forcing developer mode on. The in-game leader-customization face cycler skips reserved faces *unless developer mode is active*:

- `AoWEPACK.TFaceResourceList.NextFace` and `.PrevFace` walk faces and skip any whose record byte `[face+0x28] != 0` (the Reserved / Designer-Only flag) — **but** they first call `AoWReg.TAoWRegistry.GetDeveloper()`, and if it returns true they accept the reserved face instead of skipping.
- Vanilla `GetDeveloper` = `33 C0 C3` (`xor eax,eax; ret` → always FALSE → reserved always hidden in-game).
- AoW+ patched it to `33 C0 40 C3` (`xor eax,eax; inc eax; ret` → always TRUE → dev mode always on → reserved faces never skipped). That is the changelog entry.

The editor side was never touched by AoW+ (`AoWEd.dev.exe` / our `AoWDevX.exe` is byte-identical vanilla vs AoW+). The designer sets the flag in the editor, which writes byte `[face+0x28]`; only the *game-side* filter needed restoring.

## RE findings
- **GetDeveloper** @file `0x3A44` — AoW+ value `33 C0 40 C3` (returns true). Its three callers:
  - `NextFace` @VA `0x5574D62E`
  - `PrevFace` @VA `0x5574D672`
  - `TAoWHSMapKeyboard.KeyDown` @VA `0x55773EC3` (the AoW+ dev keyboard).
- In each face function the sequence is roughly `call GetDeveloper; test al,al; jne <accept-reserved>` followed by the reserved-flag check. Flipping GetDeveloper to false would restore the filter **but** also kill the dev keyboard. The surgical fix instead neutralises only the two face-function branches.

## The patch (final, surgical — preserves dev mode)
NOP the `jne <accept>` after `test al,al` in both face functions so the reserved-flag check ALWAYS runs regardless of the dev flag; leave GetDeveloper = true.

| Function | File offset | VA | Old | New |
|---|---|---|---|---|
| PrevFace `jne` | `0x4CA4D` | `0x5574D64D` | `75 0F` | `90 90` |
| NextFace `jne` | `0x4CA90` | `0x5574D690` | `75 0F` | `90 90` |

GetDeveloper @file `0x3A44` is **left** at AoW+ `33 C0 40 C3` (true) so the dev keyboard still works.

**Binary verification:** diffing `AoWEPACK.dll.bak_predevfix` against the next-feature snapshot shows *exactly* these two 2-byte ranges and nothing else; both offsets are still `90 90` in the current live `AoWEPACK.dll` (no later patch overlaps them).

## Revert
Write `75 0F` back at file `0x4CA4D` and `0x4CA90` (GetDeveloper is already true), or restore `AoWEPACK.dll.bak_predevfix`.

## Landmines & notes
- An earlier (user-confirmed working) approach reverted GetDeveloper itself @`0x3A44` to vanilla `33 C0 C3 90` (return false). It restored the filter but **disabled AoW+'s dev keyboard**, so it was replaced by the surgical NOP version above.
- Do not confuse these two `jne`s with the `call GetDeveloper` sites at `0x5574D62E` / `0x5574D672`; the byte edits are on the branch a few bytes later (`0x5574D64D` / `0x5574D690`).
