---
name: ghidra-mcp-setup
description: "How to bring the Ghidra MCP bridge up for AoWx RE (install, JDK 21 requirement, launch, IPv4/IPv6 gotcha)"
metadata: 
  node_type: memory
  type: reference
  originSessionId: 363e8ad2-56ec-4ede-b38d-8eb55d00d2fc
  modified: 2026-08-11T00:15:31.292Z
---

**Ghidra + MCP bridge setup for AoWx reverse-engineering (working 2026-08-09).**

INSTALL LIVES IN THE PROJECT FOLDER (not the stale copy under `AoW Misc Files\ghidra_11.0.3_PUBLIC` — that one's project is gone):
- Ghidra 11.3.2: `<game>\Ghidra\ghidra_11.3.2_PUBLIC\` (launcher `ghidraRun.bat`)
- Project: `<game>\Ghidra\AoWx Claude Ghidra.gpr` (+ `.rep`) — binaries already analyzed (AoWx.exe base 0x400000, CODE 0x401000+; also AoWEPACK etc.)
- GhidraMCP plugin: `<game>\Ghidra\GhidraMCP-release-1-4\` (GhidraMCP-1-4.zip + bridge_mcp_ghidra.py)

**JDK REQUIREMENT (the blocker):** Ghidra 11.3.2 needs **JDK 21**. Machine had JDK 25/17/8 — all rejected (25 too new, 17 too old), so `ghidraRun.bat` silently exits with no process. FIX (done): portable Temurin JDK 21 downloaded (Adoptium API `.../v3/binary/latest/21/ga/windows/x64/jdk/hotspot/normal/eclipse`) to `<game>\Ghidra\jdk21\jdk-21.0.12+8`, and pointed Ghidra at it via **`<game>\Ghidra\ghidra_11.3.2_PUBLIC\support\launch.properties` line `JAVA_HOME_OVERRIDE=<that path>`**. Non-invasive; doesn't touch system Java.

**LAUNCH:** `Start-Process ghidraRun.bat`. Ghidra restores last session; MCP HTTP server on :8080 comes up ONLY once a PROGRAM is open in CodeBrowser (project window alone = no server). If it opens to just the project, double-click AoWx.exe.

**IPv4/IPv6 GOTCHA:** the GhidraMCP server may bind to `::` (IPv6). It answered on BOTH `127.0.0.1` and `[::1]` once the program finished loading, so the earlier "connection refused" was just the server not up yet (program still loading) — retry after ~a few seconds with the program open. If it ever truly only binds IPv6, add `-Djava.net.preferIPv4Stack=true` to launch.properties VMARGS and restart.

**VERIFY:** `curl -s http://127.0.0.1:8080/segments?limit=3` → should print Headers/CODE/DATA ranges. Then `mcp__ghidra__*` tools work.

**2026-08-10 NOTES:** (1) The GUI often restores to just the project window — no program open ⇒ no :8080 server, and there's no remote way to open one (needs a human double-click). (2) The project contains ONLY AoWx.exe + AoWEPACK.dll — **AoWTCPCK/HSEPack/Network RE is done WITHOUT Ghidra** via BXL's `reference files/BXL/re_tools/dasm.py <module> <va> [len]` (annotated capstone, resolves exports/import-thunks/strings; also `xref.py <module> <va>` for callers, and aowsyms.get_symbols for export/IAT maps + VMT-slot resolution). Killing a stale GUI leaves `*.lock` files next to the .gpr — delete them before headless/next launch. Warp Self stage 2 was RE'd entirely with dasm.py.
