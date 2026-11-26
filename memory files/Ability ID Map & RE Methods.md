# Ability ID Map & How to Derive Any Ability ID (AoWEPACK.dll)

General-purpose reference: the verified name→id map for a large set of AoW1 abilities, plus the reverse-engineering **method playbook** for pinning down *any* ability's id. Ability ids are the `edx` passed to **GetAbility 0x557501c0** and are stored at **[ability+0xc]** (each ability's Create sets it). VA = file_offset + 0x55700C00.

## Useful sequential id blocks
These are contiguous ranges (very handy once you have an anchor):
- **Immunities 0x06–0x0D** (damage-type order, matches the RStr-global memory order): Magic 0x06, Fire 0x07, Cold 0x08, Lightning 0x09, Poison 0x0A, Death 0x0B, Holy 0x0C, Physical 0x0D.
- **Strikes 0x0E–0x14**: Fire 0x0E, Cold 0x0F, Lightning 0x10, Poison 0x11, Death 0x12, Holy 0x13, Magic 0x14.
- **Bolts 0x78–0x7C**: Black 0x78, Magic 0x79, Frost 0x7A, Lightning 0x7B, Holy 0x7C.
- **Shoot/throw hurls** (built by CreateHurl 0x5576ed48): Hurl Boulder 0x18, Hurl Stones 0x19, Fire Cannon 0x2c, Fire Musket 0x2d, ShootJavelin 0x39, ShootBlackJavelin 0x3A.

## Other verified ids
Web 0x1B, Dominate 0x1C, Seduce 0x1D, FlameThrowing 0x1E, **Marksmanship 0x20**, InvokeDeath 0x23, TurnUndead 0x26, NightVision 0x27, Entangle 0x28, Leadership 0x2E, Healing 0x2F, Seduced 0x30, Spellcasting 0x34, Invisibility 0x36, Doom Gaze 0x37, DispelMagic 0x3C, SelfDestruct 0x41, Possess 0x6A, Possessed 0x6B, Charge 0x6F, DragonSlaying/"Monster Slaying" 0x70, Parry 0x71, RoundAttack 0x72, ExtraStrike 0x73, FirstStrike 0x74, WallCrushing 0x75, Lifestealing 0x76, Construct 0x7D, Hero(Resurrected) 0x80/0x82 (vestigial — see note), FireBreath 0x93, Charm 0x94, Charmed 0x95, Dominated 0x96.

## The RE method playbook (in reliability order)
1. **Inline-Create scan (most abilities).** An ability's Create does `mov dword [reg+0xc], <id>` then loads its name: `mov eax, <NameRStr>` shortly after (e.g. FlameThrowing sets id 0x1E). Scan the ability code region for `c7 4X 0c <id32>`, disassemble ~0x60 bytes, and map the id to the `*RStr` global loaded nearby. Confirms Dominate 0x1C, Healing 0x2F, Spellcasting 0x34, etc.
2. **RStr export table (name → name-global VA).** `pefile` DIRECTORY_ENTRY_EXPORT on `*RStr` gives each ability name-global's address (e.g. FireImmunityRStr 0x557097AC, MarksmanshipRStr 0x5570991C, DragonSlayingRStr 0x55709AA4).
3. **RStr memory order = id order — but ONLY inside the strike/immunity block (0x557097A4–0x5570981C).** Validated by 6 strikes + Death 0x0B / Holy 0x0C all landing on the same order. **Do NOT trust this for the general RStr cluster at 0x55709844+** — there Leadership/Healing/Invisibility etc. do *not* track memory order (it wrongly suggests e.g. Marksmanship=0x30 or WallClimbing=0x20). Two adjacent anchors matching can be coincidental; validate with ≥3.
4. **RegisterAbility map.** Find every `call 0x55750238` (RegisterAbility); the `call <Create>` just before each is that ability's constructor — read the `[obj+0xc]` id it sets. The big vanilla block is @0x557715C0+; more ability creates live in 0x557Bxxxx.
5. **Class-based abilities with NO inline name (Leadership, Marksmanship, and other leveled ones).** Their Create sets only id + level data; the name comes from a virtual method, so there is **no static RStr reference** to grep. Two ways in:
   - **Shared leveled base-ctor.** All leveled abilities call the same base constructor `0x55765168`. Enumerate its callers → you get every leveled ability with its id in one shot (Leadership 0x2E, Spellcasting 0x34, Marksmanship 0x20, etc.).
   - **VMT / vmtSelfPtr trick.** Find the class VMT via its class-name ShortString `\x14T<Name>Ability` in .rdata; the dword pointing at it is the VMT's vmtClassName field. The class is instantiated as `mov eax,[vmtSelfPtr]; call <Create>` where **vmtSelfPtr** (a VMT field, here at VMT_base−0x40, holding the VMT base itself) is the class reference. Find that `mov eax,[vmtSelfPtr]` and read the id in the Create it calls. (Worked example: Marksmanship class-name ptr @0x557B7124 → VMT base 0x557B7144, vmtSelfPtr @0x557B7104, Create @0x557BBCF8 sets id **0x20**.)
6. **Per-level cost.** A leveled ability's Create adds each level via `mov edx,<level>; mov ecx,<cost>; call 0x55702eb4` (ecx = skill-point cost). Some mods wrap this in a cave that loops the levels.

## Diagnosing a wrong id when adding an ability to a chooser/list
If you add an id and **nothing at all appears** (no wrong ability either), the id is either unregistered (`GetAbility` returns null) or **registered but its `CanExpand` rejects the actor** (e.g. a status-type ability that units never "learn"). This is how two wrong Hero Slaying/Marksmanship candidates were caught. Wrong ids are *safe* in a guarded chooser — GetAbility-null / CanExpand-false just skips them, no crash.

## ⚠️ Note on "Hero Slaying"
A repurposed status ability (`TResurrected`, id **0x80 / 0x82**) is vestigial "Hero Slaying" — its CanExpand rejects hero learning, so it can never enter a level-up chooser. The *working* Hero Slaying is a separate leveled `TMultiLevelAbility` at id **0x38** (3 levels, +1/+1…+3/+3 vs heroes/leaders), registered from a PIC cave via the leveled base-ctor 0x55765168. Use 0x38.
