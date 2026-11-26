---
name: ability-id-map
description: "Reference: verified ability name→id map (AoWEPACK.dll) for 30 abilities used by the hero-AI chooser, + the RE methods to derive any ability id (inline-Create scan, RStr-memory-order ONLY within the strike/immunity block, vmtSelfPtr trick for class-based abilities, hurl/reskin registration). Extends [[aowx-re-reference]]; used by [[hero-ai-levelup-chooser]]."
metadata:
  node_type: memory
  type: reference
  originSessionId: ae619055-3278-433b-b71b-cf21e5789ad7
  modified: 2026-07-25T02:15:56.238Z
---

Ability ids are the `edx` to **GetAbility 0x557501c0** and stored at **[ability+0xc]** (set in each ability's Create). Derived & cross-validated 2026-07-24.

## VERIFIED NAME → ID (the 30 chooser abilities)
Archery 0x16 · Charge 0x6F · Cold Immunity 0x08 · Cold Strike 0x0F · Death Immunity 0x0B · Death Strike 0x12 · Dominate 0x1C · Doom Gaze 0x37 · Extra Strike 0x73 · Fire Immunity 0x07 · Fire Strike 0x0E · First Strike 0x74 · Frost Bolts 0x7A · Healing 0x2F · **Hero Slaying 0x38** · Holy Immunity 0x0C · Holy Strike 0x13 · Leadership 0x2E · Lifestealing 0x76 · Lightning Bolts 0x7B · Lightning Immunity 0x09 · Lightning Strike 0x10 · Magic Bolts 0x79 · **Marksmanship 0x20** · Monster Slaying 0x70 · Parry 0x71 · Poison Strike 0x11 · Round Attack 0x72 · **Seeker Bolts 0x3A** · Spellcasting 0x34.

## USEFUL ID BLOCKS (sequential)
- **Immunities 0x06–0x0D** (damage-type order in RStr memory): Magic 0x06, Fire 0x07, Cold 0x08, Lightning 0x09, Poison 0x0A, Death 0x0B, Holy 0x0C, Physical 0x0D.
- **Strikes 0x0E–0x14**: Fire 0x0E, Cold 0x0F, Lightning 0x10, Poison 0x11, Death 0x12, Holy 0x13, Magic 0x14.
- **Bolts 0x78–0x7C**: Black 0x78, Magic 0x79, Frost 0x7A, Lightning 0x7B, Holy 0x7C.
- **Shoot/throw (CreateHurl 0x5576ed48)**: ShootJavelin 0x39, **ShootBlackJavelin 0x3A** (reskinned by user → "Seeker Bolts").
- Known others: DragonSlaying/"Monster Slaying" 0x70, Parry 0x71, RoundAttack 0x72, ExtraStrike 0x73, FirstStrike 0x74, WallCrushing 0x75, Leadership 0x2E, Healing 0x2F, Spellcasting 0x34, Seduced 0x30, Construct 0x7D, FireBreath 0x93, Web 0x1B, Seduce 0x1D, FlameThrowing 0x1E, TurnUndead 0x26, InvokeDeath 0x23, Entangle 0x28, DispelMagic 0x3C, Charm 0x94/Charmed 0x95/Dominated 0x96, Possess 0x6A/Possessed 0x6B.

## ⚠️ HERO SLAYING = 0x38, NOT 0x82
Two Hero Slayings exist in this mod: **0x38** = the CURRENT one (mod's new `TMultiLevelAbility`, 3 levels +1/+1…+3/+3 vs heroes/leaders, registered from a PIC cave create @0x5580E31E via leveled base-ctor 0x55765168, name "Hero Slaying" AnsiString in a cave). **0x82** = the ABANDONED early attempt (repurposed `TCombatResurrectedAbility`, a status never normally granted → its CanExpand rejects hero learning → silently guarded out of the chooser). Use 0x38.

## RE METHODS TO DERIVE AN ABILITY ID (in reliability order)
1. **Inline-Create scan** — most abilities' Create does `mov [reg+0xc], <id>` then `mov eax,<NameRStr>` (e.g. FlameThrowing sets 0x1E). Scan `c7 4X 0c <id32>` in ability code (~0x5576A000–0x5577C000), map to the RStr loaded within ~0x60 bytes. Confirms Dominate 0x1C, Healing 0x2F, Spellcasting 0x34, etc.
2. **RStr export table** — `pefile` DIRECTORY_ENTRY_EXPORT for `*RStr` gives each name-global's VA (e.g. FireImmunityRStr 0x557097AC, MarksmanshipRStr 0x5570991C).
3. **RStr memory-order = id-order — ONLY inside the strike/immunity block 0x557097A4–0x5570981C.** Validated by 6 strikes + Death 0x0B/Holy 0x0C. ❌ **UNRELIABLE for the general RStr cluster 0x55709844+** (there Leadership/Healing/etc. do NOT track memory order — it gave wrong guesses like Marksmanship=0x30/WallClimbing=0x20).
4. **Registration map** — find all `call RegisterAbility(0x55750238)` sites; the preceding `call <Create>` is that ability's ctor; read its `[obj+0xc]` id. Master block @0x557715C0+; more in 0x557Bxxxx.
5. **Class-based abilities w/ NO inline name (Marksmanship, Leadership — name comes from a virtual method, no static RStr ref):** find the class VMT via its class-name ShortString (`\x14T<Name>Ability`) → the dword pointing to it is vmtClassName; the **vmtSelfPtr** (holds VMT base, ~ base-0x40 here) is loaded by the instantiation `mov eax,[vmtSelfPtr]; call <Create>`. Read the id in that Create. (Marksmanship: VMT classname ptr @0x557B7124, vmtSelfPtr @0x557B7104→VMT 0x557B7144, Create 0x557BBCF8 sets id **0x20**.) Also: callers of the shared **leveled base-ctor 0x55765168** enumerate all leveled abilities (Leadership 0x2E, Spellcasting 0x34, Marksmanship 0x20, Hero Slaying 0x38, …).
6. **Level cost** for leveled abilities: create adds each level via `mov edx,<lvl>; mov ecx,<cost>; call 0x55702eb4` (or mod cave 0x5580dff0 which loops levels). ecx = per-level skill-point cost.

**"No unfamiliar ability appeared" symptom** when adding an id to the chooser = that id is registered but its **CanExpand returns false for heroes** (not hero-learnable) OR GetAbility null. That's how 0x82(HeroSlaying-vestigial) and 0x32 were caught as wrong. Wrong ids are SAFE (guard skips them, no crash).
