---
name: recall-animate-rdtsc
description: 2026-11-14 Recall Spirits / Animate Dead raised-unit type roll used RDTSC (MP desync + TCAI errors report) → System.@RandInt (patch_recall_animate_rng_v1); list of other rdtsc sites still to review
metadata:
  type: project
---
MP report 11/14: Recall Spirits on 6 corpses (yeti, hero, …) raised 4 puppets + "Error - TCAI …" dialogs. Spawn caves (RS 0x5580D98D, AD ~0x5580CE0D; unit-class table 293 B + d100) rolled with `rdtsc … div 100` → different unit per machine. `patch_recall_animate_rng_v1.py` (.bak_raiserng) APPLIED: sites 0x5580D99B / 0x5580CE26 → `mov eax,100 / call 0x55701080 (@RandInt thunk) / mov ecx,eax`. Untested in MP. User confirmed the battle was multiplayer; exact error text unknown (Error Log will catch the next one).
**Review 11/14 (user: check them all):** the other `0F 31` hits were FALSE POSITIVES (tails of `imul eax,eax,0xF / xor edx,edx` and `shr eax,0xF / xor ..`): AoWEPACK 0x55819121, 0x55824347, 0x55824702, TCPCK 0x438E07, 0x438F98, 0x44BAC3 are deterministic arithmetic / state-seeded hash rolls (unit index, counts, getters). An alignment-voting scan over all code sections of AoWEPACK/AoWTCPCK/AoWx/HSEPack/aowInt/Network/Enginep finds no remaining rdtsc; AoWEPACK and AoWTCPCK import no time functions. So RS + AD were the only clock-based rolls.
