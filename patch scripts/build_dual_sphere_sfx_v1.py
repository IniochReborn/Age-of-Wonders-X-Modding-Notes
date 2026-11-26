#!/usr/bin/env python3
r"""
Layered sound effects for the dual-sphere spells -> Sfx\Zsp\DUALDF_*.WAV (2026-10-06).

The engine's per-spell sound list cannot layer two files on one event (a list entry picks ONE of its files), so
the layers are mixed here into new 16-bit PCM 22050 Hz mono files, built only from sounds already shipped in Sfx\:
  DUALDF_BLOODBATH.WAV  Kain BLOODUP (blood rush) + GROWL2 under it + two HEARTB beats  -> Bloodbath cast
  DUALDF_HFLOOP.WAV     Great Hail's WIND loop + ZigDSpirit wail (eerie, comet-like)          -> Hellfire while falling
  DUALDF_HFHIT.WAV      Great Hail's A_FORCE1 crunch + WraithDeath banshee wail (trimmed)     -> Hellfire per impact
Pure python (wave + array; no numpy): linear resampling, gain, offset, fade-out, peak normalisation to -1 dBFS.
Dry run prints the mix plan; --apply writes the files (our own files only -> --revert deletes them).
Remember: build_release_zip.py's namelist does not pick up NEW files by itself.
"""
import argparse, array, math, os, random, sys, wave
import sys as _sys; _sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import game_dir, game_file   # 2026-10-11: de-baked

GAME = game_dir()   # 2026-10-11: de-baked (AOW_GAME_DIR or parent of patch scripts)
SFX = os.path.join(GAME, "Sfx")
OUTDIR = os.path.join(SFX, "Zsp")
RATE = 22050

# (output name, [(source relative to Sfx  OR  "synth:whistle:<f0>:<f1>:<seconds>", gain, start s, max length s or
#                 None, fade-out s)])
# v2 (2026-10-07, user feedback): Hellfire's bed is no longer the hail wind - it is a synthesised falling whistle
# (fireworks-before-the-bang, 1900 -> 320 Hz) under a death scream and a faint spirit wail; Bloodbath builds up
# eerily (ghost appear + dark spirit + heartbeats) and is punctuated by a sword stab + Kain hit + splat at 1.75 s.
# v3 (2026-10-07): Bloodbath = loud eerie build-up (ghost appear + dark spirit + ghoul + demon growl + 3 heartbeats,
# ~2.9 s = the sword's descent at 4 ticks/frame) punctuated at STAB_AT by a bare sword stab (no vocal grunt);
# Hellfire loop = ghoulish wraith shrieks (no whistle); each impact has its own shriek: three variants (crunch +
# a different, pitch-shifted shriek) the engine picks from at random.  A layer tuple may carry a 6th value = speed
# (pitch factor; 1.2 = higher/shorter).  24-bit sources are supported.
# STAB_AT: the sword reaches the unit at effect tick 60 (12 fade-in + 8 hold + 40 descent, 1 tick/frame);
# 2.4 s assumes ~25 ticks/s - adjust after watching it (a lower value = earlier stab).
STAB_AT = 1.7           # 2.4 s was "too late" in game -> the combat ticks faster than 25/s; tune further if needed
MIXES = {
    "DUALDF_BLOODBATH.WAV": [("selecte from hk/dream_ghost_appear.wav", 2.2, 0.00, STAB_AT + 0.2, 0.25),   # loud, creepy build-up
                             ("ZZkill/ZigDSpirit.wav", 1.8, 0.00, STAB_AT + 0.3, 0.3),
                             ("xSFX/ghoul.wav", 1.4, 0.25, 1.6, 0.25),
                             ("Kain/SUCK.wav", 1.0, 0.10, 1.7, 0.3),
                             ("Kain/DEMR.wav", 0.9, 0.55, None, 0.3, 0.8),
                             ("Kain/HEARTB.wav", 1.3, 0.20, None, 0.0),
                             ("Kain/HEARTB.wav", 1.4, 0.70, None, 0.0),
                             ("Kain/HEARTB.wav", 1.5, 1.20, None, 0.0),
                             ("Attack/A_Sword2.WAV", 1.1, STAB_AT, None, 0.0),                            # the stab
                             ("Zatk/JavelinHit.wav", 0.8, STAB_AT + 0.02, None, 0.0),
                             ("synth:drone:98:2.8", 1.6, STAB_AT + 0.10, None, 0.4),                       # new creepy enchantment sting (synth, not a stock sample)
                             ("selecte from hk/dark_spell_get.wav", 0.6, STAB_AT + 0.10, 2.2, 0.5),
                             ("Kain/CHOIR2.wav", 0.5, STAB_AT + 0.25, None, 0.5, 0.75)],                  # low slowed choir under it
    # v4 (2026-10-09): the user found the START weird (WraithDeath's hard onset at 0 s) and wants a Mind-Decay-like
    # texture in it while keeping the screeching: Mind Decay's own MDECAY.WAV (5.2 s hollow drone) opens the loop
    # with a fade-in and runs under everything, the shrieks come in later and each fades IN instead of cutting in.
    # v6 (2026-10-11): the loop now starts at the CAST (portal patch v21) and the stones fall 50 ticks (~1.45 s at
    # ~35 ticks/s) later: the whole file swells from silence to full over LOOP_RISE (FADE_IN below), only the
    # MDECAY drone (x2, overlapped) sits under the rise - every shriek/hard onset comes in after it - and the file
    # runs ~6.8 s to outlast the rain (~tick 185 = 5.3 s).
    # v6 (2026-10-16, user: the wind/shriek as the stones start should fade in smoother): the shrieks start a little
    # earlier with 0.45-0.95 s fade-ins instead of 0.1-0.3 s.
    "DUALDF_HFLOOP.WAV":    [("Attack/MDECAY.WAV", 1.0, 0.00, 4.2, 0.8, 1.0, 0.20),
                             ("Attack/MDECAY.WAV", 0.8, 0.90, 4.2, 0.8, 0.94, 0.60),
                             ("Zu/WraithDeath.wav", 0.9, 1.30, None, 0.3, 0.85, 0.95),
                             ("xSFX/ghoul.wav", 0.8, 1.85, None, 0.4, 1.0, 0.70),
                             ("Zu/ReaperDeath.wav", 0.7, 2.55, 2.4, 0.5, 1.0, 0.55),
                             ("Attack/MDECAY.WAV", 0.7, 3.40, 3.4, 1.0, 0.9, 0.50),
                             ("Hit_Death/Screech3.WAV", 0.5, 3.75, None, 0.4, 0.8, 0.45),
                             ("Zu/WraithDeath.wav", 0.6, 4.60, None, 0.6, 0.80, 0.30)],
    # v5 (2026-10-10): the crunch was "hard to hear" - the shriek started 30 ms in at 0.75 and the whole mix was
    # normalised to the SUM of the two, so the crunch sat at roughly half of Great Hail's level.  Now the crunch is
    # the event: A_Force1 (Great Hail's own impact) doubled with A_Force2 on top, the shriek comes in only after
    # the transient (0.16 s, faded in, at a third of the level) and the file is driven through the soft clipper
    # like the loop, so the crunch lands at full scale and stays as loud and distinct as Great Hail's.
    "DUALDF_HFHIT1.WAV":    [("Attack/A_Force1.WAV", 1.0, 0.00, None, 0.0),
                             ("Attack/A_Force2.WAV", 0.9, 0.01, None, 0.0),
                             ("Zu/WraithDeath.wav", 0.35, 0.16, 1.0, 0.35, 1.0, 0.08)],
    "DUALDF_HFHIT2.WAV":    [("Attack/A_Force1.WAV", 1.0, 0.00, None, 0.0),
                             ("Attack/A_Force2.WAV", 0.9, 0.01, None, 0.0, 0.94),
                             ("Zu/WraithDeath.wav", 0.35, 0.16, 0.9, 0.35, 1.18, 0.08)],
    "DUALDF_HFHIT3.WAV":    [("Attack/A_Force1.WAV", 1.0, 0.00, None, 0.0, 0.96),
                             ("Attack/A_Force2.WAV", 0.9, 0.01, None, 0.0),
                             ("Hit_Death/Screech3.WAV", 0.3, 0.18, 0.9, 0.3, 0.9, 0.08),
                             ("Zu/WraithDeath.wav", 0.25, 0.22, 0.8, 0.3, 0.92, 0.08)],
    # 2026-10-13: REPENT (206).  Sound 0 plays at the cast (caster site) and must carry the whole build-up: the motes
    # (~1.4 s of soft shimmer), then the thread of light appearing (a charge-up), then the choir/spirit swell as the
    # beam widens toward the hit at ~2.4 s after the first strike.  Sound 1 = the landing (kind-0x0A impact).
    # v2 (2026-10-13, user): "more choir like, then beam sfx, then turn undead when it hits".  Sound 0 = a CHOIR chord
    # (CHOIR2 stacked at three pitches, each fading in) during the motes, then a synthesized BEAM hum/shimmer from
    # ~1.4 s (the thread of light) swelling to the hit at ~2.5 s; sound 1 = plain vanilla TurnUnd (set in the pipeline).
    # v3 (2026-10-13, "sounds janky"): consonant intervals only (root + a fifth, no third), every layer with a long
    # fade-in AND fade-out so nothing starts or stops abruptly, an airy pad under the whole thing, overlapping choir
    # copies so the 2 s sample never ends audibly, a softer beam hum crossfading in as the choir fades, no transient.
    # v4 ("keep polishing"): the choir gets a pseudo-reverb (delayed, quieter copies at 0.12/0.26 s, one an octave
    # down for weight), the beam hum gets a real texture under it (the Radiance laser charge, slowed and doubled).
    # v5 (2026-10-13, "choir should be constant for the duration of the spell animation, until the hit"): the 2 s choir
    # sample is tiled every 0.8 s with 0.6 s crossfades (root + fifth + an octave-down copy) at a steady level for
    # ~3.9 s, the beam hum rides under it from ~1.3 s, everything fades together at the end (= the hit).
    "DUALDF_REPENT.WAV":    [("Zu/HolySpiritDeath.wav", 0.35, 0.00, 3.4, 1.0, 1.0, 0.50)]                        # airy pad under everything
                            + [("Kain/CHOIR2.wav", 1.15, t, 1.3 if t > 3 else None, 1.2 if t < 3 else 0.9, 1.000, 0.2, 0, 0.6) for t in (0.0, 0.8, 1.6, 2.4, 3.2)]      # root, tiled (v7: choir up, "too subtle")
                            + [("Kain/CHOIR2.wav", 0.62, t + 0.05, 1.2 if t > 3 else None, 1.0 if t < 3 else 0.8, 1.498, 0.2, 0, 0.6) for t in (0.0, 0.8, 1.6, 2.4, 3.2)]   # a fifth up
                            + [("Kain/CHOIR2.wav", 0.48, t + 0.10, 1.6 if t > 2 else 2.0, 0.8, 0.500, 0.7) for t in (0.0, 1.4, 2.8)]   # an octave down (slow copies last 4 s)
                            + [("synth:beam:220:2.6", 1.25, 1.30, None, 0.7, 1.0, 0.55),                         # v6: the beam hum, louder and clearer
                               ("synth:beam:440:2.4", 0.55, 1.40, None, 0.7, 1.0, 0.60),                         #   an octave up for presence
                               ("selecte from hk/radiance_laser_prepare.wav", 0.5, 1.35, None, 0.3, 0.72, 0.30), # beam texture (slowed laser charge)
                               ("selecte from hk/radiance_laser_prepare.wav", 0.4, 2.10, None, 0.4, 0.66, 0.30),
                               ("selecte from hk/focus_health_heal.wav", 0.35, 1.60, None, 0.5, 1.0, 0.30)],     # shimmer on top of the beam
    # REPENT hit (sound 1, at the landing), 2026-10-13: a custom holy smite instead of vanilla TurnUnd - a hard bright
    # transient (dream-hit + parry ping) over a slowed low thud, a choir chord struck a fifth apart, the airy spirit
    # tone as the tail and a shimmer fading out.
    # v3 ("too similar to the choir, make it something else, magical"): no choir - a hard hit transient, the Dream Nail
    # slash (an ethereal magical strike), a magic-missile impact, a slowed thud for weight, an orb chime and a heal
    # shimmer as the magical after-ring.
    # v4 ("sounds too much like a laser"): the Dream Nail slash and the magic missile are out; the strike is a hard
    # transient over a slowed thud, a synthesized holy BELL (inharmonic partials, long decay) as the magical body, an
    # orb chime, the airy spirit tone and a shimmer as the tail.
    # v5 ("more like Turn Undead but different somehow"): Turn Undead itself is the body, but detuned into a chorus
    # (a copy a little low and a copy a little high, slightly late), shortened with a fade, with a hard transient and
    # a slowed thud on the front and the holy bell + shimmer ringing on afterwards.
    "DUALDF_REPHIT.WAV":    [("Attack/EnchP03.WAV", 0.45, 0.00, 0.14, 0.02, -1.4, 0.06),           # v6 (user: v5 too friendly, like a buff - holy but more INTENSE):
                             ("selecte from hk/dream-hit.wav", 1.0, 0.12, None, 0.15),            #   a sharp reversed holy in-suck slamming into a heavy
                             ("Attack/A_Force1.WAV", 0.8, 0.12, None, 0.3, 0.7),                  #   impact (bright hit + low force thump + shockwave),
                             ("Attack/Shockw.wav", 0.6, 0.12, 1.0, 0.8, 0.9, 0.0, 0, 2.5),   # r8: rumble cut shorter on a steep curve
                             ("synth:bell:262:2.0", 0.7, 0.12, None, 0.8),                        #   a LOW struck bell clang (fifth on top),
                             ("synth:bell:392:1.7", 0.45, 0.13, None, 0.7),
                             ("synth:choir:130.8:1.3", 0.55, 0.11, None, 0.5),                    #   a short deep choir burst
                             ("Attack/MagicA02.WAV", 0.5, 0.12, 0.9, 0.4, 0.85),
                             ("Attack/TurnUnd.WAV", 0.12, 0.12, 1.9, 1.0, 1.0)],                    #   v7: a barely-there Turn Undead underneath for depth                 #   and a hot magic burst (no sparkle tail)
    # HARVEST SOULS (207), 2026-10-13: sound 0 at the cast = the souls being drawn out (whirl + motes ~3 s until the
    # pop at strike tick 99): Mind Decay hollow drone under a slowed Reap Soul, a sucking draw and a ghoul moan;
    # sound 1 = the pop at the caster: the corpse-essence collect chime + dark spell get + the vanilla ENCHN01 under it.
    "DUALDF_HARVEST.WAV":   [("Attack/MDECAY.WAV", 0.9, 0.00, 3.6, 0.9, 1.0, 0.30),
                             ("Zatk/ReapSoul.wav", 0.8, 0.25, None, 0.4, 0.85, 0.20),
                             ("Kain/SUCK.wav", 0.7, 0.60, 2.4, 0.5, 0.9, 0.30),
                             ("xSFX/ghoul.wav", 0.5, 1.10, None, 0.5, 0.9, 0.30),
                             ("synth:rattle:15:8:1.9", 1.1, 1.55, None, 0.3, 1.0, 0.08),                       # v2: creepy k-k-k-k death rattle (was the slowed 2nd Reap Soul = the "horn")
                             ("synth:rattle:11:6:1.4", 0.6, 2.40, None, 0.4, 1.0, 0.10)],
    # v2 (2026-10-13, "the last sfx plays too late"): the mix only reached half level 0.4 s in (dark_spell_get swells,
    # the collect chime is quiet) - now a hard transient at 0 (dream-hit), the chime louder, the swell as the tail.
    # v3 (2026-10-13, "replace the horn sound with a spooky sound like Terror / the old end sfx"): the Terror spell's
    # own cue IS the old end sound (vanilla Terror = ENCHN01) - so ENCHN01 carries the pop, with the hit transient on
    # top and a low spirit wail underneath; the collect chime and the dark-spell swell (the "horn") are gone.
    # (v3 = ENCHN01-led "Terror" pop was rejected 10/13 -> back to v2)
    "DUALDF_HARVPOP.WAV":   [("selecte from hk/dream-hit.wav", 0.9, 0.00, None, 0.15),                          # the pop itself, at 0
                             ("selecte from hk/dream_essence_corpse_collect.wav", 1.5, 0.00, None, 0.3),
                             ("selecte from hk/dark_spell_get.wav", 0.6, 0.00, 1.8, 0.5),
                             ("Attack/ENCHN01.WAV", 0.5, 0.00, 2.0, 0.6)],
    # ---- Life/Fire (2026-10-13).  MARTYR = holy enchant chime + a choir swell + a flame whoosh and a bell;
    # CLEANSE = fire ignition + holy chime + heal shimmer, a crackle tail; PHOENIX = the Mermaid summon cue + a fire
    # spiral + a bird screech over a choir; STARLOOP = wind + tiled choir + beam hum + fire (the hail loop role);
    # STARHIT1/2 = crunch + fireball burst + a bell (two variants the engine picks at random).
    "DUALDF_MARTYR.WAV":    [("Attack/EnchP02.WAV", 0.9, 0.00, None, 0.3),          # 10/13 v3: the ORIGINAL 1.5 s mix (v2 remix "got worse"), same layers/timing, only the choir/fire/bell tails run ~0.5 s longer
                             ("Kain/CHOIR2.wav", 0.9, 0.10, 2.7, 0.7, 1.0, 0.25),
                             ("Kain/CHOIR2.wav", 0.5, 0.15, 2.5, 0.7, 1.498, 0.30),
                             ("Kain/FLAMESW.wav", 0.8, 0.35, None, 0.3),
                             ("Attack/Fireloop.WAV", 0.35, 0.50, 2.0, 0.7, 1.0, 0.30),
                             ("synth:bell:523:2.0", 0.4, 0.40, None, 0.5),
                             ("selecte from hk/focus_health_heal.wav", 0.3, 0.60, None, 0.5)],
    "DUALDF_CLEANSE.WAV":   [("Attack/FireStrt.WAV", 1.0, 0.00, None, 0.3),
                             ("Kain/FLAMESW2.wav", 0.8, 0.05, None, 0.3),
                             ("Attack/EnchP01.WAV", 0.7, 0.10, None, 0.4),
                             ("selecte from hk/focus_health_heal.wav", 0.5, 0.25, None, 0.5),
                             ("synth:bell:659:1.4", 0.35, 0.30, None, 0.5),
                             ("Kain/BURN.wav", 0.5, 0.60, 1.5, 0.6, 1.0, 0.20)],
    "DUALDF_PHOENIX.WAV":   [("Attack/Magic01.WAV", 0.9, 0.00, None, 0.4),
                             ("selecte from hk/flamebearer_fire_spiral_cast.wav", 0.8, 0.05, None, 0.4),
                             ("Attack/Fireloop.WAV", 0.5, 0.20, 2.2, 0.7, 1.0, 0.30),
                             ("Hit_Death/BirdScr.WAV", 0.9, 0.90, None, 0.3, 0.9),
                             ("Kain/CHOIR2.wav", 0.45, 0.60, None, 0.6, 1.498, 0.40)],
    # v4 (2026-10-13, "meh, try something else"): the LOOP is now a cathedral - the airy spirit pad under a slow
    # tiled choir (root + fifth), a soft rising bell arpeggio and only a whisper of wind; each HIT = the crunch under
    # a short Turn Undead chorus (the body of Repent's hit, which worked) + a high bell + the heal shimmer tail.
    # v5 (2026-10-13, "sounds bad, try again"): a different palette altogether - the LOOP is the vanilla Resurrect
    # cue (the game's own angelic sound) opening over a soft choir bed and a heal shimmer, no wind, no bells; each HIT
    # is a holy CRACK (the lightning sample, short) with a tight Turn Undead chord and a soft chime - no boulder crunch.
    "DUALDF_STARLOOP.WAV":  [("Attack/Ressur.WAV", 1.0, 0.00, 4.5, 1.0),
                             ("Attack/Ressur.WAV", 0.55, 2.20, 3.0, 1.0, 1.26)]
                            + [("Kain/CHOIR2.wav", 0.55, t, None, 0.7, 1.0, 0.5) for t in (0.3, 1.1, 1.9, 2.7, 3.5, 4.3)]
                            + [("selecte from hk/focus_health_heal.wav", 0.4, t, None, 0.6, 1.0, 0.3) for t in (0.5, 2.0, 3.5)],
    # v6: "sounds ok but is missing crunch" -> the A_Force1 crunch is back under each hit
    # ASHES TO ASHES (353), 2026-10-13: one cue (the ray class plays sound 0 at the cast) = corpses igniting with an
    # evil hiss: fire ignition + flame whoosh, Vaporize's hiss (the user's reference) over it, a ghoul moan and the
    # Mind Decay hollow drone underneath, a dark spell swell as the tail.
    # v2 (user): the corpses burning = a FIRE sound with a magical sound added - ignition + flame whoosh + crackling
    # burn + a short fire loop, with the airy shimmer and a soft enchant chime on top; the Vaporize hiss / ghoul / drone gone.
    "DUALDF_ASHES.WAV":     [("Attack/FireStrt.WAV", 0.9, 0.00, None, 0.3),
                             ("Kain/FLAMESW.wav", 0.7, 0.08, None, 0.3),
                             ("Kain/BURN.wav", 0.7, 0.15, 1.8, 0.6),
                             ("Attack/Fireloop.WAV", 0.5, 0.20, 1.6, 0.6, 1.0, 0.0),
                             ("synth:shimmer:2.0", 0.4, 0.10, None, 0.0),
                             ("Attack/EnchP02.WAV", 0.35, 0.30, None, 0.4)],
    # ASHES TO ASHES hit (sound 0, v2): the ashes engulf the target - Vaporize's hiss (the user's reference) with a
    # fire ignition and a crunch under it, a short ghoul rasp, a dark sting tail.
    # v5 (user: "sfx needs work"): sound 0 plays ONCE per cast (caster animation at the first strike) and must carry the
    # whole hit phase (~10 ticks per hit) - a sustained whirl: a flame whoosh spinning up, a pitched fire crackle held
    # under it for ~2.5 s with a second higher layer, a long rising-then-holding whirl whistle, the ash hiss, and a
    # soft dark swell at the end; no ghoul/explosion.
    # v6 (user: v5 "sounds like Vaporize / a motor winding; make it fire and wind"): a gusting wind bed, a flame whoosh,
    # the natural-pitch fire loop and a crackling burn under it, a dragon-breath roar for body, a late lick of flame;
    # no whistle, no Vaporize, no pitch-shifted loops.
    # v7 (user): no Vaporize at all, the fire distinct during the swirl, the wind more magical -> wind bed + an airy
    # shimmer on top, the fire loop and crackle up front, a flame lick mid-way; the dragon roar dropped.
    # v8 (user: still "a Vaporize-like sound" = the band-passed wind noise; wants a MORE POWERFUL fire than the corpses +
    # a magical sound): no noise bed at all - a big fire (two whooshes, the fire loop and a double crackle, a low dragon
    # roar for weight, flame licks) with the shimmer and a soft drone sting as the magic.
    # v9 (user: "not epic enough"): a deep pitched-down whoomp on the onset (not a crack), both whooshes louder, the
    # dragon roar bigger and lower, a choir swell and a stronger drone for the magic, the shimmer kept.
    "DUALDF_ASHHIT.WAV":    [("Kain/EXPLODE.wav", 0.5, 0.00, 1.4, 0.6, 0.75, 0.0),
                             ("Kain/FLAMESW2.wav", 1.0, 0.00, None, 0.3),
                             ("Kain/FLAMESW.wav", 0.85, 0.15, None, 0.3),
                             ("Attack/Fireloop.WAV", 1.0, 0.05, 2.8, 0.7, 1.0, 0.0),      # v10 (user: more distinct fire + crackling): three crackle layers, two fire loops, more licks
                             ("Attack/Fireloop.WAV", 0.6, 0.40, 2.4, 0.7, 1.12, 0.0),
                             ("Kain/BURN.wav", 1.0, 0.10, 2.6, 0.6),
                             ("Kain/BURN.wav", 0.75, 0.55, 2.2, 0.6, 0.92, 0.0),
                             ("Kain/BURN.wav", 0.6, 1.20, 1.8, 0.6, 1.06, 0.0),
                             ("Attack/DBreath.WAV", 0.6, 0.05, 2.4, 0.7, 0.78, 0.0),
                             ("Attack/FlameA.WAV", 0.75, 0.80, None, 0.4),
                             ("Attack/FlameA.WAV", 0.55, 1.70, None, 0.4),
                             ("Attack/FireStrt.WAV", 0.6, 1.30, None, 0.4),
                             ("Kain/CHOIR2.wav", 0.4, 0.20, 2.6, 0.8, 0.9, 0.3),
                             ("synth:shimmer:3.0", 0.5, 0.05, None, 0.0),
                             ("synth:drone:110:2.6", 0.35, 0.25, None, 0.0)],
    # ASHES per-hit impact (sound 1, v11): a short fire puff with a soft thump - played by the engine on every landing.
    "DUALDF_ASHIMPACT.WAV": [("Attack/FireStrt.WAV", 0.9, 0.00, 0.8, 0.3),
                             ("Attack/A_Force1.WAV", 0.35, 0.00, None, 0.0),
                             ("Kain/BURN.wav", 0.5, 0.05, 0.7, 0.4),
                             ("Attack/FlameA.WAV", 0.45, 0.08, 0.6, 0.4)],
    # ---- Earth/Fire (2026-10-13)
    # v2 (user: "sfx sucks, refer to Geyser"): Geyser = SFX\MOVES\WATERLG.WAV - the big water gush leads, thick and
    # pitched down for oil, with a ground rumble under it and the slime sloshes of Ooze as it settles.
    # v3 (2026-10-17, user: "sfx doesn't match gfx anymore"): timed from the RISE (cue 0 now plays at the rise spawn,
    # patch_tc_oilgush_cue0_v1.py): ground rupture + eager gush at 0, a slower deeper gush holding the steady fountain
    # through the landings (1.8-2.7 s; the per-landing slimes are the engine's cue 1), fading over the collapse
    # (2.8-3.4 s) with the column sloshing back into the pool.  The baked 0.9/1.3 s slimes are gone.
    "DUALEF_OILSPRING.WAV": [("Attack/Earth.WAV", 0.6, 0.00, 0.9, 0.5),                       # ground rupture
                             ("Attack/A_Force1.WAV", 0.45, 0.00, None, 0.2, 0.7),              # the crack/thump as it bursts
                             ("Moves/waterlg.WAV", 1.0, 0.00, None, 0.5, 1.0, 0.03, 0.35),     # eager gush (skips the source's slow swell)
                             ("Moves/waterlg.WAV", 0.8, 0.80, 2.65, 0.5, 0.72, 0.5, 0.3),      # steady fountain, deeper; fades 2.95-3.45
                             ("Attack/Earth.WAV", 0.3, 0.90, 2.0, 0.6, 0.75, 0.4),             # low rumble under the fountain
                             ("Moves/SlimeS1.WAV", 0.55, 2.80, None, 0.2, 0.6),                # column falls back into the pool
                             ("Moves/SlimeS4.WAV", 0.45, 3.05, None, 0.2, 0.55)],
    # v4 (2026-10-14, user: "forget the magical sfx and only keep the roar, but make the roar deeper and more guttural"):
    # Fury's roar (A_MONST2) pitched well down, doubled lower again, soft-clipped hard (drive) for the gravel.
    # v7 (2026-10-14, user: "really quiet; just a roar, louder, slowed down (longer + a bit deeper)"): Fury's roar alone
    # at 0.82x speed, driven hard (tanh soft clip = denser/louder at the same -1 dB peak), no other layer.
    "DUALEF_LIONHEART.WAV": [("Attack/A_Monst2.WAV", 1.0, 0.00, None, 0.25, 0.82, 0.0)],
    # ---- Fire/Air (2026-10-14): 388 Sandstorm / 389 Implosion / 390 Frenzied Charge / 391 Drought
    # v2 (user: redo): a howling desert wind with gusts, and a dry whump of sand per landing
    "DUALFA_SANDSTORM.WAV": [("Attack/Tornado.wav", 0.9, 0.00, 3.2, 0.9),                      # the howl
                             ("Attack/Windloop.WAV", 0.7, 0.00, 3.2, 1.0, 1.1, 0.3),            # wind bed
                             ("Attack/Wind.WAV", 0.6, 0.90, None, 0.6, 0.85, 0.2),              # a lower gust
                             ("Attack/Earth.WAV", 0.25, 0.30, 2.0, 0.8, 1.6, 0.3)],            # grit hiss
    "DUALFA_SANDHIT.WAV":   [("Attack/Wind.WAV", 0.8, 0.00, 0.45, 0.2, 1.6, 0.0),             # a short rush of sand
                             ("Attack/A_Force1.WAV", 0.5, 0.03, 0.4, 0.2, 0.9, 0.0)],          # dry whump
    # v2 (user): the circle's sound = the crack + thud they liked, plus something fiery, under a short in-rush; the
    # landing then plays Fireball's own BLAST (vanilla cue, set in the pipeline).
    # v3 (user: the magical sound plays first, during the circle, BEFORE the explosion): a reversed magic swell +
    # the in-rush + fire catching, ending as the ring closes (~1 s); Fireball's BLAST then plays at the landing.
    # v11 (user: v10 sounds pretty good - make it more EPIC and FULL): v10 plus a second growl-horn an OCTAVE DOWN
    # (40 -> 85 Hz) winding up in parallel, a sub-bass swell (38 -> 62 Hz) and Fireball's BLAST reversed back in for a
    # bigger in-suck; driven a touch harder; still 0.95 s, hard cut at the close.
    "DUALFA_IMPLOSION.WAV": [("synth:growlhorn:80:170:0.95", 1.0, 0.00, None, 0.0),             # the winding growl-horn
                             ("synth:growlhorn:40:85:0.95", 0.7, 0.00, None, 0.0),              # an octave down = fuller
                             ("synth:subswell:38:62:0.95", 0.55, 0.00, None, 0.0),             # sub-bass swell
                             ("Attack/MagicA01.wav", 0.5, 0.00, 0.95, 0.02, -0.9),            # reversed magic swell
                             ("Attack/FireStrt.WAV", 0.3, 0.10, 0.85, 0.1, 0.8),              # crackling grit
                             ("Attack/Explod1.wav", 0.45, 0.00, 0.95, 0.02, -0.78),           # reversed deep in-suck
                             ("Attack/BLAST.WAV", 0.35, 0.10, 0.85, 0.02, -0.9)],             # reversed blast in-suck
    # Fire/Water (2026-10-14).  Scald (405): cue 0 = cast (the caster's cast animation, at the strike) = a deep steam
    # surge (Vaporize's own sound pitched down + the Geyser's water surge); cue 1 = the landing hiss (every hit).
    # Blood Boil (404): one cue at the strike - a thick bubbling boil + sizzle, then a short roar as the Bloodlust takes hold.
    "DUALFW_BLOODBOIL.WAV": [("Attack/m_Water.WAV", 1.0, 0.00, 1.3, 0.4, 0.7),                 # thick, slow bubbling (v2 louder)
                             ("Attack/FireStrt.WAV", 0.55, 0.05, 1.1, 0.4, 0.9),              # sizzle
                             ("Attack/A_Monst2.WAV", 0.65, 0.55, 0.9, 0.4, 1.05),             # the bloodlust roar
                             ("Attack/Vapor.wav", 0.12, 0.00, 1.2, 0.5, 0.95),                # v2: Vaporize's sound, barely noticeable
                             ("synth:hiss:1.3", 0.9, 0.05, None, 0.0),                        # v3 (user: more of a hiss)
                             ("Attack/FireStrt.WAV", 0.35, 0.35, 0.9, 0.4, 1.3)],             # v3: a higher sizzle
    # Steam Power (406) v2 (user: too explosive - the Builder's Guild + a battering ram rolling): cue 0 = the guild's
    # hammering over heavy wheels rolling (HvyWh = the siege-engine move sound) and a soft steam hiss swelling in;
    # cue 1 = the puff hiss replayed by the map-wide animation.
    "DUALFW_STEAMPOWER.WAV": [("Places/BGuild.WAV", 1.3, 0.00, 2.6, 0.6),                      # the workshops hammering (v4 louder)
                              ("Moves/HvyWh1.WAV", 0.7, 0.10, 1.4, 0.4),                      # the ram rolling
                              ("Moves/HvyWh2.WAV", 0.6, 1.10, 1.4, 0.5),
                              ("synth:hiss:2.0", 0.35, 0.40, None, 0.0)],                      # v3: a soft synthesized hiss (Vapor.wav carried a blast)
    "DUALFW_STEAMPUFF.WAV":  [("synth:hiss:0.7", 0.6, 0.00, None, 0.0),                        # v3: the per-hex puff = a soft hiss, no transient
                              ("Places/BGuild.WAV", 0.3, 0.00, 0.7, 0.3)],                     # v4 (user: layer the Builder's Guild sound in): a quiet hammering snippet
    # Scald (405) v1 restored (user 2026-10-14: v2's louder mix was worse): cue 0 = cast = a deep steam surge
    # (Vaporize's sound pitched down + the Geyser's water surge); cue 1 = the landing hiss (every hit).
    "DUALFW_SCALD.WAV":     [("Attack/Vapor.wav", 0.9, 0.00, 1.4, 0.4, 0.8),                    # steam surge, deeper
                             ("Moves/waterlg.WAV", 0.6, 0.05, 1.2, 0.5, 0.9),                  # the geyser's water surge
                             ("Attack/m_Water.WAV", 0.3, 0.20, 1.0, 0.5, 1.2)],                # a bubbling fizz
    "DUALFW_SCALDHIT.WAV":  [("Attack/Vapor.wav", 0.9, 0.00, 0.9, 0.4, 1.2),                    # sharp scalding hiss
                             ("Attack/FireStrt.WAV", 0.45, 0.02, 0.8, 0.4)],                   # the crackle
    # Earth/Death summons (2026-10-14): the summon chime + the beast.
    "DUALED_DIREWOLF.WAV":  [("Attack/Magic01.WAV", 0.8, 0.00, 1.6, 0.5),                       # the summon chime
                             ("Kain/GROWL1.wav", 0.75, 0.45, 1.4, 0.4)],                       # the dire wolf's growl
    "DUALED_WEREWOLF.WAV":  [("Attack/Magic01.WAV", 0.8, 0.00, 1.8, 0.5, 0.85),                 # a deeper summon chime
                             ("Kain/GROWL2.wav", 0.8, 0.35, 1.4, 0.4, 0.9),                    # the werewolf's snarl
                             ("Hit_Death/D_Wolf.WAV", 0.55, 1.05, 1.5, 0.6, 0.75)],            # a long, low howl-like cry
    # Thousand Threads (335) v2 (user: sfx meh - try another): cue 0 = a dry, creepy skittering swarm (crawling legs)
    # with a papery flutter and a faint taut-silk whine; cue 1 = per landing = a soft sticky snag (a crawl tick + slime).
    "DUALED_THREADS.WAV":   [("Moves/Crawl1.WAV", 1.0, 0.00, 1.6, 0.5),                         # skittering legs
                             ("Moves/Crawl2.WAV", 0.8, 0.50, 1.4, 0.5, 1.1),
                             ("Moves/Flutter.WAV", 0.6, 0.15, 1.2, 0.5, 0.8),                 # papery flutter
                             ("synth:hiss:1.4", 0.25, 0.10, None, 0.0)],                       # a faint silky rustle
    "DUALED_THREADHIT.WAV": [("Moves/Crawl2.WAV", 0.9, 0.00, 0.35, 0.2, 1.3),                   # a quick tick
                             ("Moves/SlimeS3.WAV", 0.75, 0.02, 0.4, 0.2, 1.2)],                 # sticky snag
    # Golden Age (302): cue 0 = the cast = the treasury's gold chime under a warm, rising enchantment shimmer.
    # Awaken Spirit (300): a magic chime, a faint spirit-animal call and a soft shimmer.  Blessing of the Forest (301):
    # the sacred-grove ambience (rustling, birds) under a warm blessing chime.
    # Awaken Spirit v4 (user: v3 sucks - a MAGICAL sound during the initial animation (High Prayer's rising motes,
    # ~0-3.3 s), then a ROAR during the final spinning aura (tick 100 ~3.3 s; the timing the user confirmed on the
    # Forest swell); the roar = Fury's A_MONST2, slightly modified): a sustained magic build (Magic03 slowed + the
    # long EnchP03 shimmer swelling in), then Fury's roar slowed 0.85 with a lower 0.7 double and a short echo.
    "DUALEL_AWAKEN.WAV":    [("Attack/Magic03.WAV", 0.8, 0.00, 2.2, 0.6, 0.8),                  # the magic begins
                             ("Attack/EnchP03.WAV", 0.6, 0.30, 3.0, 0.4, 1.0, 1.2),            # a long shimmer building to the roar
                             ("Attack/A_Monst2.WAV", 1.0, 3.30, 1.6, 0.6, 0.85),               # Fury's roar, a touch slower/deeper
                             ("Attack/A_Monst2.WAV", 0.5, 3.32, 1.6, 0.6, 0.70),               # a lower double for weight
                             ("Attack/A_Monst2.WAV", 0.25, 3.62, 1.6, 0.8, 0.85)],             # echo
    # Blessing of the Forest v3 (user: the swell's timing is right but the sound is lame - try another): the grove,
    # then the Shrine of Life's own radiant hum + a bright chime ~3.3 s in as the aura peaks.
    "DUALEL_FOREST.WAV":    [("Places/SGrove.WAV", 0.9, 0.00, 2.4, 0.8),                        # rustling grove, birds
                             ("Attack/EnchP01.WAV", 0.6, 0.10, 1.6, 0.6, 0.9),                 # blessing chime
                             ("Attack/Ressur.WAV", 0.9, 3.25, 2.4, 0.8),                       # v4: Resurrection's radiant holy swell as the aura peaks
                             ("Attack/m_Earth.wav", 0.5, 3.20, 2.2, 0.8, 0.9, 0.2)],           # the Earth sphere's own cast, low under it (rooted, earthy)
    # Earth/Air (2026-10-14).  Hurl Boulder (365): cue 0 = the throw = the catapult's creak and release under a heavy
    # whoosh; cue 1 = the landing = a crunching rock crash over a deep thud.  Gravity Well (366): cue 0 = a deep pull -
    # a sub-bass swell gliding DOWN, Earth's rumble slowed and the wind played backwards (air sucked in); cue 1 = per
    # hex = a heavy slam as the targets are dragged to the ground.
    # Hurl Boulder v2 (10/15; user: the ability's sfx with an added magical sound at start-up, hit = the ability's):
    # a short magic chime, then the ability's own CATAPULT.WAV unchanged; the hit cue points at vanilla A_PUNCH2.WAV.
    # v3 (10/15; user: more magical noise): cue 0 now starts at the pre-throw glow (patch_hurlboulder_glow_v1.py) and the
    # throw leaves at tick 18 (~0.6 s): a magic chime + rising enchantment shimmer + a soft synth shimmer over 0-0.6 s,
    # a bright magic sparkle on the release, then the ability's CATAPULT.WAV unchanged at 0.6 s.
    # v5 (10/15; user: the magic noise is lame - try another; the start-up is now the boulder shaking and rising from
    # the ground for ~1.0 s, the throw at tick 30): the Earth sphere's own cast (m_Earth) as the magic, a low earthy
    # rumble under it, grinding stone as the rock tears free and rises (~0.35-0.95 s), then the ability's CATAPULT.WAV
    # at 1.0 s (kept loud: magic layers moderate, drive 2.2).
    # v6 (10/15; user: replace the crackling at the beginning with a brief spurt of the Tremors sfx = SFX\ATTACK\EARTH.WAV)
    "DUALEA_BOULDER.WAV":   [("Attack/Earth.WAV", 0.9, 0.00, 0.65, 0.3),                        # a brief spurt of Tremors as the ground cracks
                             ("xSFX/stones.wav", 0.5, 0.35, 0.65, 0.3, 0.9),                  # grinding stone as it rises
                             ("Attack/Catapult.WAV", 1.0, 1.00, None, 0.0)],                  # the ability's throw
    "DUALEA_GRAVITY.WAV":   [("synth:subswell:95:32:1.8", 0.8, 0.00, None, 0.2),                # the pull: a sub swell gliding down
                             ("Attack/Earth.WAV", 0.7, 0.10, 1.8, 0.6, 0.75),                  # Earth's rumble, slowed
                             ("Attack/Wind.WAV", 0.45, 0.00, 1.6, 0.4, -1.0)],                 # wind reversed = air sucked in
    "DUALEA_GRAVHIT.WAV":   [("Attack/Explod1.wav", 0.8, 0.00, 1.2, 0.5, 0.6, 0.0),             # a heavy, low slam
                             ("xSFX/stones.wav", 0.4, 0.02, 0.6, 0.4, 0.8)],
    # Overgrowth (383, Earth/Water 2026-10-15): the rustling grove under the Earth and Water spheres' casts and a low
    # enchantment swell - growth, life, water.
    # Swampwalk (382, 10/15; user: needs a custom sfx): a soft enchantment chime over the swamp - buzzing insects,
    # three squelching footsteps in the mud, a swimmer's splash and a low watery swell.
    # v2 (10/15; user: louder, and the magic and the mud LAYERED together, not one after the other): every layer starts
    # at 0 s - the chime and the squelching steps together - and the mix is driven (tanh 2.0) for loudness.
    "DUALEW_SWAMPWALK.WAV": [("Attack/EnchP01.WAV", 0.7, 0.00, 1.4, 0.6, 0.9),                  # the enchantment
                             ("Moves/Insect1.WAV", 0.35, 0.00, 1.4, 0.6, 1.0, 0.15),          # swamp insects
                             ("Moves/SlimeS1.WAV", 0.9, 0.00, 0.5, 0.2),                      # squelching steps, from the start
                             ("Moves/SlimeS2.WAV", 0.8, 0.35, 0.5, 0.2, 0.95),
                             ("Moves/SlimeS3.WAV", 0.9, 0.70, 0.5, 0.2, 1.05),
                             ("Moves/M_Swim1.WAV", 0.7, 0.20, 0.8, 0.4),                      # a swimmer's splash
                             ("Moves/waterlg.WAV", 0.45, 0.00, 1.4, 0.6, 0.8, 0.1)],          # watery swell
    # World Healer v2 (2026-10-17, user: too recognizable): the Shrine of Life slowed (0.86x, offset past its opening
    # chime) under a reversed swell of itself; Resurrection only as a faint reversed breath INTO a sung major choir
    # chord (replacing its familiar forward swell); the Water cast slowed; a soft shimmer + low bell - the land
    # breathing again.
    "DUALLW_WORLDHEALER.WAV": [("Places/SoLife.WAV", 0.45, 0.00, 1.0, 0.2, -0.95, 0.4),
                             ("Places/SoLife.WAV", 0.7, 0.70, 2.4, 1.0, 0.86, 0.3, 0.6),
                             ("Attack/Ressur.WAV", 0.35, 0.10, 1.2, 0.15, -1.1, 0.6),
                             ("synth:choir:196:2.4", 0.38, 1.05, None, 1.0),
                             ("Attack/m_Water.WAV", 0.42, 0.25, 2.6, 0.9, 0.9),
                             ("synth:shimmer:2.2", 0.2, 0.9, None, 0.9),
                             ("synth:bell:392:2.0", 0.16, 1.1, None, 0.9)],
    # Blessed Dew (326, Life/Water 2026-10-15): a blessing chime and a soft bell over a low watery swell and a faint
    # dawn grove.
    "DUALLW_BLESSEDDEW.WAV": [("Attack/EnchP01.WAV", 0.9, 0.00, 1.8, 0.7),
                             ("synth:bell:784:1.6", 0.35, 0.15, None, 0.5),
                             ("Moves/waterlg.WAV", 0.4, 0.05, 1.8, 0.7, 0.85, 0.2),
                             ("Places/SGrove.WAV", 0.3, 0.00, 2.0, 0.8)],
    # Bountiful Harvest (325, Life/Water 2026-10-15): coins over a rustling grove and Life Mastery's own ALIGHT, softened.
    "DUALLW_HARVEST.WAV":   [("Events/Gold.WAV", 0.9, 0.00, 1.6, 0.5),
                             ("Places/SGrove.WAV", 0.55, 0.00, 2.2, 0.8),
                             ("Places/ALIGHT.WAV", 0.5, 0.15, 2.0, 0.8, 1.0, 0.2),
                             ("Events/Gold.WAV", 0.45, 0.60, 1.2, 0.5, 1.15)],
    # Holy Water (324, Life/Water 2026-10-15): one cue per cast - a rushing splash of water and a bright holy chime together.
    "DUALLW_HOLYWATER.WAV": [("Moves/waterlg.WAV", 0.9, 0.00, 1.3, 0.5, 1.2),
                             ("Moves/M_Swim1.WAV", 0.8, 0.05, 0.9, 0.4),
                             ("Attack/EnchP01.WAV", 0.7, 0.00, 1.4, 0.6, 1.05),
                             ("Attack/Ressur.WAV", 0.35, 0.10, 1.4, 0.7, 1.1)],
    # Soul Siphon (340) v3 (10/15; user: more SINISTER): no bright chimes - a deep drone and a sub-bass swell, the
    # Death sphere's cast reversed and slowed, a slow deep suck, a slowed ghoulish wail and a demonic growl under it.
    "DUALWD_SOULSIPHON.WAV": [("synth:drone:55:2.2", 0.8, 0.00, None, 0.6),
                             ("synth:subswell:60:30:1.6", 0.55, 0.20, None, 0.4),
                             ("Attack/m_Death.wav", 0.6, 0.00, 1.8, 0.3, -0.75, 0.4),
                             ("Kain/SUCK.wav", 0.85, 0.40, 1.4, 0.5, 0.72),
                             ("xSFX/ghoul.wav", 0.6, 0.15, 1.6, 0.6, 0.8),
                             ("Kain/GROWL2.wav", 0.5, 0.60, 1.4, 0.6, 0.7),
                             ("Places/Teleport.WAV", 0.45, 0.00, 2.2, 0.7, 0.5),            # v5 (user: deeper/more sinister, more subtle)
                             ("Places/Teleport.WAV", 0.25, 0.10, 2.0, 0.7, -0.42, 0.4)],    #   + a reversed, even deeper copy
    "DUALWD_BLACKTIDE.WAV": [("Attack/m_Water.WAV", 0.8, 0.00, 2.4, 0.8, 0.8),
                             ("Moves/waterlg.WAV", 0.55, 0.10, 2.2, 0.8, 0.75),
                             ("Attack/m_Death.wav", 0.35, 0.30, 2.0, 0.8, 0.85),
                             ("synth:subswell:70:34:1.8", 0.5, 0.20, None, 0.4)],
    # Plague (341, Water/Death 2026-10-15): Mind Decay's rot, a swarm of flies and a low sick drone.
    "DUALWD_PLAGUE.WAV":    [("Attack/MDECAY.WAV", 0.9, 0.00, 2.0, 0.7),
                             ("Moves/Insect1.WAV", 0.6, 0.10, 2.0, 0.7, 0.9),
                             ("Moves/Insect2.WAV", 0.4, 0.40, 1.6, 0.7, 1.1),
                             ("synth:drone:73:2.0", 0.5, 0.00, None, 0.6)],
    # Nimue's Favour (398, Water/Air 2026-10-15): the Water sphere's cast, a bright blessing chime and shimmer, and a
    # faint lakeside grove.
    "DUALWA_NIMUE.WAV":     [("Attack/m_Water.WAV", 0.8, 0.00, 2.2, 0.8),
                             ("Attack/EnchP01.WAV", 0.6, 0.20, 1.6, 0.6, 1.05),
                             ("Attack/EnchP02.WAV", 0.45, 0.50, 1.6, 0.7),
                             ("Places/SGrove.WAV", 0.3, 0.00, 2.4, 0.8)],
    # Ice Age (399, Water/Air 2026-10-15): a howling cold wind, the creak and crack of ice (vanilla ICE), the Water
    # sphere's cast slowed and a low drone.
    "DUALWA_ICEAGE.WAV":    [("Attack/Wind.WAV", 0.8, 0.00, 2.6, 0.9, 0.85),
                             ("Attack/Ice.WAV", 0.8, 0.20, 1.6, 0.6, 0.85),
                             ("Attack/m_Water.WAV", 0.5, 0.10, 2.4, 0.8, 0.8),
                             ("synth:drone:65:2.4", 0.4, 0.00, None, 0.7)],
    # Misty Step (396) v2 (user: sfx sucked + too quiet + include a splash): a reversed wind rush as the caster melts to
    # mist, an airy shimmer, the Teleport whoosh, then a big water splash (Moves/waterlg + a swim splash) as they reform.
    # v3 (user: v2 didn't sound like a splash - it should be HEAVY splashing in water): the synthesised heavy splash
    # (plunge thump + wash + glugs + droplet patter) over Moves/waterlg slowed (deeper), two swim splashes slowed and
    # staggered for the churn, and only a faint shimmer of the mist.
    "DUALWA_MISTYSTEP.WAV": [("synth:splash:1.6", 1.0, 0.00, None, 0.0),
                             ("Moves/waterlg.WAV", 0.9, 0.00, 1.6, 0.6, 0.75),
                             ("Moves/M_Swim1.WAV", 0.8, 0.05, 0.9, 0.3, 0.7),
                             ("Moves/M_Swim2.WAV", 0.7, 0.30, 0.9, 0.3, 0.8),
                             ("Hit_Death/Splat.wav", 0.35, 0.00, 0.5, 0.2, 0.6),
                             ("synth:shimmer:1.2", 0.15, 0.00, None, 0.0)],
    # Flashfreeze (397) v2 (user: an Implosion-like shrinking-circle sound but icy, then a triple ice sound for the hits):
    # DUALWA_FFRING = the ring closing in (icy whistle sliding up, reversed ice crackle + reversed Iceloop in-suck, a
    # sub swell, a glassy shimmer); DUALWA_FLASHFREEZE = one hit (vanilla Ice crack + AIce crunch + a bright bell), played
    # once per strike.
    # v4 (user: still bad): Implosion's OWN ring recipe (growl-horn wind-up + octave + sub swell + reversed in-sucks) moved
    # up a fifth and dressed in ice - the fire grit swapped for reversed ice cracks/crackle, a glassy shimmer and two
    # crystal glints on top.
    # v5 (user: ring -> hits felt janky): stretched to 1.25 s so it builds right up to the ring's collapse, the reversed in-sucks
    # landing at the end, overlapped by the first hit sound.
    # v6 (user: as the sounds overlap, fade the first one out): everything fades over its last 0.3 s, ending at 1.35 s - the
    # first hit sound (~1.17 s) comes in over the fade.
    "DUALWA_FFRING.WAV":    [("synth:growlhorn:120:255:1.35", 0.8, 0.00, None, 0.3),             # Implosion's winding horn, a fifth up
                             ("synth:growlhorn:60:128:1.35", 0.55, 0.00, None, 0.3),              # its octave down
                             ("synth:subswell:38:62:1.35", 0.5, 0.00, None, 0.3),                 # the same sub swell
                             ("Attack/MagicA01.wav", 0.45, 0.55, 0.8, 0.3, -0.9),               # reversed magic swell (as Implosion)
                             ("Attack/Ice.WAV", 0.6, 0.55, 0.8, 0.3, -0.85),                    # reversed ice crack = in-suck
                             ("Attack/Iceloop.WAV", 0.45, 0.00, 1.35, 0.3, -1.0),                # reversed ice crackle (the grit)
                             ("synth:shimmer:1.35", 0.4, 0.00, None, 0.3),
                             ("synth:bell:2093:0.35", 0.2, 1.0, None, 0.25)],
    # v4: v2's hit restored (user), trimmed to 0.5 s so it ends before the next strike (>= 18 ticks apart)
    "DUALWA_FLASHFREEZE.WAV": [("Attack/Ice.WAV", 1.0, 0.00, 0.5, 0.2, 1.05),
                             ("Places/AIce.wav", 0.6, 0.00, 0.5, 0.2, 1.2),
                             ("synth:bell:1568:0.5", 0.3, 0.00, None, 0.25)],
    # ---- Air/Death (2026-10-15).  Suffocate (345) v2 (user: ONE long sound for the whole cast, no restart per hit: air
    # drawn out of the lungs, then gasping for air): a long rising suck (reversed wind + vacuum climbing, a hollow low
    # drone) for ~1.3 s, cut, then ragged gasps (short reversed breathy wind bursts + a strangled grunt).
    "DUALAD_SUFFOCATE.WAV": [("synth:glide:Attack/Vapor.wav:0.55:1.5:3.6:0.65", 1.0, 0.00, None, 0.4)],   # v13 (user: higher sooner + slightly higher, and fade out): 0.55 -> 1.5, curve ^0.65 (gentler than v11's ^0.45), FADE_OUT 1.2 s
    # Banshee Gale (344) v2 (user: v1 terrible - a mix of wind and banshee screaming, like Sandstorm but death magic):
    # ONE long cue (played once per cast - patch_banshee_v1 v2): Sandstorm's howling wind bed, the Death sphere's cast
    # slowed under it, and banshee wails riding the gusts - rising/falling synthesised shrieks plus a female death
    # scream pitched up and down.  The landing cue stays a short low thud.
    "DUALAD_BANSHEE.WAV":   [("Attack/Wind.WAV", 0.6, 0.00, 1.4, 0.6, 0.8),                      # v8 (user: start right away; screams more prominent + epic; fade out slowly, past the animation): an immediate gust
                             ("Attack/Tornado.wav", 0.55, 0.00, 7.6, 3.4, 0.7),                 # the howl, slowed
                             ("Attack/Windloop.WAV", 0.4, 0.00, 7.6, 3.4, 0.8),
                             ("Kain/CHOIR2.wav", 0.45, 0.00, 7.6, 3.4, 0.8),
                             ("Kain/CHOIR2.wav", 0.4, 2.20, 3.0, 1.0, 0.75, 0.6),            # the choir again (the sample is only ~2 s)
                             ("Kain/CHOIR2.wav", 0.35, 4.50, 3.0, 1.6, 0.7, 0.6),                    # a dark choir
                             ("synth:subswell:30:55:7.0", 0.45, 0.00, None, 3.0),
                             ("Zu/WraithDeath.wav", 1.0, 0.05, 1.66, 0.6, 0.78),                # the screams, from the start
                             ("Zu/WraithDeath.wav", 0.7, 0.10, 1.4, 0.6, 1.25),                 #   high
                             ("Zu/WraithDeath.wav", 0.75, 0.12, 2.2, 0.8, 0.55),                #   deep
                             ("xHero_Death/scream4.wav", 1.0, 0.85, 2.1, 0.8, 0.82),            # the long howling shriek
                             ("xHero_Death/scream4.wav", 0.7, 0.90, 1.8, 0.8, 1.2),             #   high
                             ("xHero_Death/scream4.wav", 0.75, 0.95, 2.6, 0.9, 0.6),            #   deep
                             ("Zu/WraithDeath.wav", 0.85, 1.80, 1.4, 0.6, 0.9),                 # a second cry as it peaks
                             ("Zu/WraithDeath.wav", 0.6, 1.85, 1.4, 0.6, 1.3),
                             ("xHero_Death/scream4.wav", 0.8, 2.80, 2.4, 1.4, 0.76),            # a last howl as it winds down
                             ("xHero_Death/scream4.wav", 0.55, 2.85, 2.6, 1.6, 0.55),
                             ("Zu/WraithDeath.wav", 0.4, 0.40, 1.66, 0.8, -0.7),
                             ("Zu/WraithDeath.wav", 0.9, 2.15, 1.66, 0.6, 0.72),                # v9: cries as the throws begin (~2.2 s, vortex v4)
                             ("Zu/WraithDeath.wav", 0.6, 2.20, 1.4, 0.6, 1.2),
                             ("xHero_Death/scream4.wav", 0.8, 3.30, 2.4, 1.2, 0.7),             # and as they land
                             ("xHero_Death/scream4.wav", 0.55, 3.35, 2.4, 1.4, 1.1)],               # a reversed, ghostly echo
    "DUALAD_BANSHEEHIT.WAV": [("Attack/Wind.WAV", 0.6, 0.00, 0.35, 0.2, 1.6),
                             ("synth:subswell:60:35:0.25", 0.5, 0.00, None, 0.1)],
    # Borrow Time (346) v2 (user: rework the sfx): a clock's tick-tock slowing down, a deep bell struck BACKWARDS (time
    # reversed) with sand hissing back up the glass, an airy shimmer, and a soft high chime as the time is lent.
    "DUALAD_BORROWTIME.WAV": [                                                               # v8 (user: the 2nd tick = the first one, slightly lower): v7 (user: "click... clock... click... clock"): the real clock's tick (click) and tock (clock, lower) alternating + a woody synth body
                             ("Events/Clock.WAV", 1.0, 0.00, 0.12, 0.03, 0.95, 0.0, 0.0),
                             ("synth:tick:2200:700:0.25", 0.5, 0.00, None, 0.05),
                             ("Events/Clock.WAV", 1.0, 0.98, 0.12, 0.03, 0.86, 0.0, 0.0),
                             ("synth:tick:1900:600:0.25", 0.5, 0.98, None, 0.06),
                             ("Events/Clock.WAV", 1.0, 1.96, 0.12, 0.03, 0.95, 0.0, 0.0),
                             ("synth:tick:2200:700:0.25", 0.5, 1.96, None, 0.05),
                             ("Events/Clock.WAV", 1.0, 2.94, 0.12, 0.03, 0.86, 0.0, 0.0),
                             ("synth:tick:1900:600:0.25", 0.5, 2.94, None, 0.06),
                             ("synth:bell:131:1.6", 0.45, 0.10, None, 0.1, -1.0),
                             ("synth:hiss:1.4", 0.35, 0.10, None, 0.3, -1.0)],
    # ---- Life/Air (2026-10-16): 308 Heavenly Chorus / 309 Inspiration / 310 Second Wind / 311 Angel Wings
    "DUALLA_CHORUS.WAV":    [("synth:choir:110:1.9", 1.0, 0.00, None, 0.0),                     # v5 (user: airy/off, jarring transitions): a SUNG chord progression
                             ("synth:choir:164.8:1.9", 0.85, 1.15, None, 0.0),                  #   A major (deep) -> E major (higher, a fifth up) ->
                             ("synth:choir:73.4:2.3", 1.0, 2.30, None, 0.0),                    #   D major (deeper) - each swelling in under the last one's release
                             ("Attack/MagicC01.WAV", 0.5, 0.00, 4.5, 1.8, 0.7, 1.8)],           # v6 (user): MagicC01 slowed to span the whole sound, slow fade in + out
    # v25 (user: still too recognizable): the Arena file dropped; a fight built from single clashes instead - A_Sword1/2/3 +
    # Parry at random pitches (0.78-1.2) and irregular gaps (0.13-0.32 s), their levels tracing the old fade-in / fade-out.
    # v24 (user: swords less recognizable): Arena pitched down ~3 semitones (0.85, heavier/slower clashes) and taken from a
    # later stretch of the file (src 1.9 s) so the clash pattern differs from the Arena site's.
    # v23 (user: a bit higher; swords fade in more subtly, out more smoothly): glide 0.78 -> 0.83, swords fade-in 0.8 s / out 1.4 s.
    # v22 (user: horn a bit lower overall, swords sooner still): glide 0.76 -> 0.81, swords in at 0.25 s (same 2.9 s end).
    # v21 (user: swords end sooner to match the gfx; horn deeper at the START then easing slightly higher): horn = glide
    # 0.80 -> 0.855 over 2.6 s (eased); swords out by 2.9 s (fade 0.8).
    # v20 (user: horn very slightly deeper, swords sooner): horn 0.86 (~2.5 semitones down), swords in at 0.5 s.
    # v19 (user: v18 bad - the Call Hero horn itself, just one note lower, then the Arena's sword fight layered in: starting after
    # the horn but before it ends, running on longer; horn fades out first, then the swords): CallHero a whole tone down (0.891),
    # held, fading out by 2.6 s; Places/Arena.wav (clashing swords, from 0.5 s in its source) fading in at 0.9 s, out by 3.8 s.
    "DUALLA_INSPIRE.WAV":   [("synth:glide:Attack/CallHero.wav:0.78:0.83:2.6:0.6", 1.0, 0.00, None, 1.0),
                             ("Places/Arena.wav", 0.36, 0.25, 2.65, 1.7, 1.2, 0.8, 0.3, 2.2),
                             ("Places/Arena.wav", 0.36, 0.25, 2.65, 1.7, 0.95, 0.8, 1.0, 2.2),
                             ("Places/Arena.wav", 0.36, 0.25, 2.65, 1.7, 0.8, 0.8, 1.7, 2.2),
                             ("Places/Arena.wav", 0.36, 0.25, 2.65, 1.7, 0.68, 0.8, 2.4, 2.2)],   # v27 (user: v26 still recognizable): FOUR Arena stretches (src 0.3/1.0/1.7/2.4) at four pitches (1.2/0.95/0.8/0.68) summed into one battle din;
    # v28 (user: fade-out more aggressive/smoother): fade 1.7 s on a (1-x)^2.2 curve
    # (the Arena pair sums two different stretches/pitches, so neither clash pattern is recognizable)
    "DUALLA_INSPHIT.WAV":   [("Attack/MagicA04.WAV", 0.30, 0.00, 0.9, 0.4, 1.0),                 # v5 (user: each circle a SUBTLE magic sound): a short bright sparkle
                             ("synth:bell:1047:0.6", 0.10, 0.00, None, 0.3)],                   #   with a faint high bell - no swell, so 7 overlapping hits can't blur into an "aahh"
    "DUALLA_SECONDWIND.WAV": [("Zig collection/HEARTB.wav", 1.0, 0.00, 0.20, 0.03, 1.15, 0.0, 0.0),
                             ("Zig collection/HEARTB.wav", 1.0, 0.20, 0.20, 0.05, 1.15, 0.0, 0.29),
                             ("Zig collection/HEARTB.wav", 1.0, 0.48, 0.20, 0.03, 1.15, 0.0, 0.0),
                             ("Zig collection/HEARTB.wav", 1.0, 0.68, 0.20, 0.05, 1.15, 0.0, 0.29),
                             ("Zig collection/HEARTB.wav", 1.0, 0.96, 0.20, 0.03, 1.15, 0.0, 0.0),
                             ("Zig collection/HEARTB.wav", 1.0, 1.16, 0.20, 0.05, 1.15, 0.0, 0.29),
                             ("Zig collection/HEARTB.wav", 1.0, 1.44, 0.20, 0.03, 1.15, 0.0, 0.0),
                             ("Zig collection/HEARTB.wav", 1.0, 1.64, 0.20, 0.05, 1.15, 0.0, 0.29),   # v6 (user: tighter): each double beat re-spaced (0.20 s apart, was 0.26) by slicing the sample; pairs every 0.48 s (was 0.55)
                             ("Attack/Wind.WAV", 0.55, 0.10, 0.35, 0.05, -1.8),                 # quick sharp breaths
                             ("Attack/Wind.WAV", 0.55, 0.62, 0.35, 0.05, -1.9),
                             ("synth:subswell:40:85:1.8", 0.5, 0.00, None, 0.4),                # power welling up
                             ("synth:glide:Kain/CHOIR2.wav:0.9:1.25:1.6", 0.5, 0.40, None, 0.5),  # strength returning
                             ("Attack/Wind.WAV", 0.75, 1.75, 1.0, 0.6, 1.2)],                   # the second wind: a fresh gust
    "DUALLA_ANGELWINGS.WAV": [("Moves/Wing1.WAV", 1.0, 0.00, 0.5, 0.15, 0.75),                   # five big, deep wing-beats, loud and up front
                             ("Moves/Wing2.WAV", 1.0, 0.42, 0.5, 0.15, 0.7),
                             ("Moves/Wing1.WAV", 1.0, 0.84, 0.5, 0.15, 0.75),
                             ("Moves/Wing2.WAV", 1.0, 1.26, 0.5, 0.15, 0.72),
                             ("Moves/Wing1.WAV", 0.9, 1.68, 0.5, 0.2, 0.78),
                             ("Moves/Air1.wav", 0.25, 0.05, 1.8, 0.6, 1.0),
                             ("synth:choir:261.6:2.3", 0.45, 0.00, None, 0.0)],                 # v5 (user: a better, slightly different choir; smoother in; lasting; out WITH the wings): a sung high C-major chord
    # Sanctify (208, Life T3 2026-10-16): cast = a sung C-major swell, the Life enchant shimmer, a struck holy bell;
    # per consecrated hex = a quiet high bell + a short bright sparkle (subtle: 7 land almost together).
    "DUALDF_SANCTIFY.WAV":  [("synth:choir:130.8:2.45", 0.8, 0.00, None, 1.6),                   # v2 (user: louder + a bit more epic, lose the recognizable HEALING
                             ("synth:choir:261.6:2.4", 0.55, 0.05, None, 1.55),                  #   sound = EnchP02 removed): choir doubled an octave up + a fifth,
                             ("synth:choir:196:2.35", 0.35, 0.10, None, 1.5),     # r10: the choir fades from ~0.85 s, after the rest (0.55 s)
                             ("synth:subswell:30:55:2.2", 0.45, 0.00, None, 1.65),               #   a sub swell under it and a low bell under the high one; driven
                             ("synth:bell:262:2.0", 0.35, 0.45, None, 1.9),
                             ("synth:bell:523:1.6", 0.2, 0.40, None, 1.45, 1.0, 0.12),
                             ("Attack/MagicC01.WAV", 0.3, 0.30, 1.8, 1.55, 1.1, 0.4)],
    "DUALDF_SANCTHIT.WAV":  [("synth:bell:1047:0.8", 0.121, 0.00, None, 0.65, 1.0, 0.06, 0, 2.2),         # v3 (user: v2 jarring - only a SOFT holy touch per circle): a faint
                             ("Attack/MagicA04.WAV", 0.088, 0.00, 0.8, 0.6, 0.9, 0.06, 0, 2.2)],          #   soft-attack high bell + a whisper of sparkle
    # Miracle (209, Life T4 2026-10-16): the vanilla resurrection (Attack/Ressur.WAV - Recall Spirit's own cast sound) under a
    # rising sung C-major swell and a soft bright shimmer.
    "DUALLI_MIRACLE.WAV":   [("synth:subswell:30:60:2.6", 0.55, 0.00, None, 1.2, 1.0, 0.3),       # v3 (user: parts must blend like ONE sound changing): the sub swell
                             ("Attack/MagicC01.WAV", 0.7, 0.00, 1.6, 0.35, -1.0, 0.4),          #   runs on under the reveal; the reversed in-rush overlaps it and
                             ("synth:choir:130.8:3.4", 0.8, 0.85, None, 0.0, 1.0, 0.70),        #   tails off as the choir already swells in underneath,
                             ("synth:choir:261.6:3.3", 0.7, 0.95, None, 0.0, 1.0, 0.70),
                             ("synth:choir:392:2.9", 0.4, 1.10, None, 0.0, 1.0, 0.60),
                             ("Attack/Ressur.WAV", 1.0, 1.15, 3.2, 1.2, 1.0, 0.25),             #   the resurrection blooms in (soft attack),
                             ("Zig collection/CHOIR2.wav", 0.55, 1.10, 3.0, 1.2, 1.0, 0.50),
                             ("synth:bell:523:2.6", 0.3, 1.30, None, 0.8, 1.0, 0.05),
                             ("Attack/EnchP03.WAV", 0.4, 1.40, 2.6, 1.0, 1.0, 0.60)],           #   and the shimmer fades in over the release
    # Undying (210, Death T2 2026-10-16): the Death sphere's cast, two slow heavy heartbeats (life that will not stop),
    # a dark minor choir swelling in and a low sub swell.
    "DUALDE_UNDYING.WAV":   [("Attack/m_Death.wav", 0.55, 0.00, 3.4, 1.1, 0.6),                  # v3 (user: the Death cast was too recognizable as Unholy Champion):
                             ("Attack/m_Death.wav", 0.28, 0.00, 1.6, 0.05, -0.8, 0.6),           #   it now runs slowed + a reversed copy swelling in, over a drone;
                             ("synth:drone:55:3.4", 0.5, 0.00, None, 1.1, 1.0, 0.5),                       # v2 (user: good - add a 2nd identical heartbeat PAIR ahead of the
                             ("Kain/HEARTB.wav", 0.88, 0.20, 0.45, 0.15, 0.8),                  #   existing one, a touch louder): pair 1 (new) ...
                             ("Kain/HEARTB.wav", 0.88, 1.00, 0.45, 0.15, 0.8),             #   all four beats now IDENTICAL copies of the first (user: later ones weird)
                             ("Kain/HEARTB.wav", 0.88, 1.90, 0.45, 0.15, 0.8),                  #   ... pair 2 (the original two beats, moved after it)
                             ("Kain/HEARTB.wav", 0.88, 2.70, 0.45, 0.15, 0.8),
                             ("synth:choir:110:3.0:minor", 0.55, 0.30, None, 1.0, 1.0, 0.5),
                             ("synth:subswell:30:50:3.0", 0.44, 0.00, None, 1.1)],
    # Call of the Dead (211, Death T4 2026-10-16): epic and necromantic, built on synths (no stock sample leads): a deep
    # swell rising from the ground and a creepy minor drone, a dark sung A-minor chord (doubled an octave down) swelling
    # in, two bone-rattle trains as the dead stir, a slowed low moan, with the Death cast and the crypt's air under it.
    "DUALDE_CALLDEAD.WAV":  [("synth:subswell:28:50:4.2", 0.6, 0.00, None, 1.4, 1.0, 0.6),
                             ("synth:drone:55:4.6", 0.7, 0.00, None, 1.6, 1.0, 0.8),
                             ("Attack/m_Death.wav", 0.45, 0.05, 3.0, 1.2, 0.72, 0.4),
                             ("synth:choir:110:4.0:minor", 0.8, 0.40, None, 1.4, 1.0, 1.0),
                             ("synth:choir:55:4.0:minor", 0.55, 0.60, None, 1.4, 1.0, 1.0),
                             ("synth:rattle:14:7:1.4", 0.585, 1.20, None, 0.5),
                             ("synth:rattle:11:6:1.6", 0.455, 2.30, None, 0.6),
                             ("synth:glide:Zu/WraithDeath.wav:0.62:0.5:3.0:0.8", 0.21, 1.00, None, 1.2),
                             ("Places/Crypt.WAV", 0.21, 0.00, 4.4, 1.5, 0.9, 0.8)],   # r3: the airy crypt + moan quieter, the rest driven harder
    # Wither (205, Death T1; 2026-10-16 user: a UNIQUE sound, creepy, sinister, branches crackling subtly - replaces the
    # vanilla ENCHN01): a low creeping minor drone and a dark minor choir breathing in, a dry slowed wind, the Death
    # sphere's cast slowed right down, and dry wood cracking in small snaps (D_Wood* sped up, quiet) as the land withers.
    "DUALDE_WITHER.WAV":    [("synth:drone:49:2.8", 0.6, 0.00, None, 1.0, 1.0, 0.5),
                             ("synth:choir:98:2.6:minor", 0.35, 0.20, None, 1.0, 1.0, 0.9),
                             ("Attack/m_Death.wav", 0.4, 0.10, 2.6, 1.0, 0.7, 0.4),
                             ("synth:rattle:11:6:1.4", 0.2, 0.75, None, 0.6)],   # r3: hissy fast rattle -> slow creak; r4: the sped-up D_Wood snaps (the "tshh") removed
    "DUALAI_GUST.WAV":      [("Attack/Tornado.wav", 1.0, 0.00, 2.3, 0.7, 0.85, 0.05),           # v5 (Gust v6 timing ~2.1 s, push ~1.65 s): the tornado roar +
                             ("Attack/Wind.WAV", 0.7, 0.00, 2.2, 0.7, 0.7, 0.05),               #   slowed gust for the whole breath, a sub swell,
                             ("synth:subswell:45:30:1.3", 0.6, 0.00, None, 0.6, 1.0, 0.15),
                             ("Moves/Air2.WAV", 0.55, 1.60, None, 0.4, 0.8),                    #   and the hurl whoosh as units hop
                             ("Moves/Air1.wav", 0.35, 1.68, None, 0.4, 0.7)],
    "DUALAI_CROSSWIND.WAV": [("synth:glide:Attack/Wind.WAV:1.0:0.62:2.0:1.4", 0.75, 0.00, None, 0.4, 1.0, 0.4),     # v7: retimed at ~34.5 ticks/s (Hellfire calibration):
                             ("synth:glide:Attack/Windloop.WAV:0.95:0.6:2.0:1.4", 0.6, 0.00, None, 0.4, 1.0, 0.5),  #   the first wind glides DOWN to the stop at ~1.97 s;
                             ("synth:glide:Attack/Tornado.wav:0.6:0.92:1.3:0.7", 1.0, 1.85, None, 0.3, 1.0, 0.45),  #   then a deep tornado roar builds and RISES as the wind
                             ("Attack/Tornado.wav", 1.0, 3.10, 2.5, 1.6, 0.92, 0.3),                                #   accelerates to 1.7x (~3.2 s), held, long fade-out;
                             ("Attack/Windloop.WAV", 0.9, 1.85, 3.7, 1.8, 1.05, 0.5),                              #   (the 'toothbrush' synth wind replaced by the real
                             ("Attack/Wind.WAV", 0.75, 2.30, 3.0, 1.6, 1.15, 0.4),                                  #   Windloop + a gust sample)
                             ("Moves/Air1.wav", 0.4, 0.40, None, 0.3, 0.8),
                             ("Moves/Air2.WAV", 0.35, 1.05, None, 0.3, 0.9),
                             ("Moves/Air2.WAV", 0.5, 2.45, None, 0.3, 0.85),
                             ("Moves/Air1.wav", 0.45, 3.05, None, 0.3, 1.0),
                             ("Moves/Air2.WAV", 0.35, 3.75, None, 0.4, 0.95),
                             ("synth:drone:41:5.6", 0.35, 0.00, None, 1.8, 1.0, 0.8),           # v8 (user: more EPIC): a low drone under everything,
                             ("synth:subswell:28:45:2.0", 0.55, 0.00, None, 0.4, 1.0, 0.9),     #   deep swells building into the turn and into the peak,
                             ("synth:subswell:30:55:2.0", 0.6, 1.95, None, 0.9, 1.0, 1.0),
                             ("Attack/Wind.WAV", 0.55, 1.30, 0.67, 0.02, -0.9, 0.25)],          #   and a reversed gust SUCKING into the dead stop (~1.97 s)
    "DUALAI_SUSPEND.WAV":   [("synth:glide:Attack/Wind.WAV:0.7:1.15:2.2:0.8", 0.8, 0.00, None, 0.8),
                             ("Attack/Tornado.wav", 0.35, 0.10, 2.0, 0.9, 0.8, 0.4),
                             ("Moves/Air1.wav", 0.5, 0.30, None, 0.3, 0.9),
                             ("Attack/EnchP01.WAV", 0.3, 0.40, 1.6, 0.8, 1.3, 0.3),
                             ("Moves/Wing1.WAV", 0.55, 1.80, None, 0.4, 0.9),                    # v3 (user: no chime - subtler): one wing flap as the unit settles
                             ("Attack/MagicA04.WAV", 0.15, 1.85, 0.8, 0.5, 0.9, 0.05)],          #   aloft, with a faint sparkle of magic
    "DUALAI_STATICSHIELD.WAV": [("Attack/StormBig.wav", 1.0, 0.00, 2.6, 1.2),                  # v2 (user: lame - much more EPIC, thunder/lightning): a thunder
                             ("Zu/AIRelehit.wav", 0.6, 0.00, None, 0.3, 0.85),                  #   crack + roll (StormBig), the electric hit, crackling arcs
                             ("Attack/Shockc.wav", 0.5, 0.15, 2.0, 0.8, 1.0, 0.1),              #   (Shockc + a fast buzz) settling into a low electric hum,
                             ("synth:rattle:30:18:1.8", 0.4, 0.30, None, 0.7),                  #   with a sub swell under the strike
                             ("synth:beam:98:2.4", 0.45, 0.30, None, 0.9, 1.0, 0.4),
                             ("synth:subswell:30:50:2.4", 0.5, 0.00, None, 1.0)],
    # Mend Walls v7 (2026-10-17 round 7, user: "only one debris at a time ... all launch one after the other" / "when
    # debris hits the wall I want a subtle crunch/hail noise, not too loud"): the cast bed only - the Earth cast, the
    # gentle Tremors rumble carrying the whole queue (pieces are flung 0.58 s .. ~2.2 s), the ground cracking as the
    # first pieces tear out (0-0.3 s), the green glow's shimmer + healing chime from the first impact (0.72 s) and two
    # soft bells near the end.  The per-hit knocks are GONE from this file: every piece's impact now plays cue 2
    # (DUALER_MENDHIT.WAV) from the engine at its real arrival tick (patch_tc_mendwalls_v2.py v7).
    "DUALER_MENDWALLS.WAV":  [("Attack/m_Earth.wav", 0.40, 0.00, 1.6, 0.7, 0.9),                 # the Earth sphere's cast
                              ("Attack/Earth.WAV", 0.50, 0.00, 2.5, 0.9, 0.82, 0.30),           # Tremors, gentled: slowed, swelling in, easing off
                              ("synth:subswell:34:50:1.8", 0.26, 0.00, None, 0.6),              # a soft sub under the trembling
                              ("Attack/Earth.WAV", 0.22, 0.00, 0.18, 0.10, 1.8),                # ground cracking open under the first debris
                              ("Attack/Earth.WAV", 0.19, 0.12, 0.18, 0.10, 1.95, 0.0, 0.3),
                              ("Attack/Earth.WAV", 0.17, 0.23, 0.18, 0.10, 1.7, 0.0, 0.6),
                              ("synth:shimmer:2.0", 0.28, 0.72, None, 0.0),                     # the green glow (from the first impact)
                              ("Attack/EnchP01.WAV", 0.34, 0.78, 1.2, 0.6, 0.95),               # a healing chime (Remedy's family)
                              ("synth:bell:392:1.4", 0.16, 2.00, None, 0.6),                    # soft bells near the end of the queue
                              ("synth:bell:587:1.0", 0.11, 2.22, None, 0.5),
                              ("synth:drone:98:2.8", 0.15, 0.00, None, 0.8)],
    # Mend Walls v7 cue 2 (played by the engine once per piece as it hits the wall, sound option honoured): a SUBTLE
    # crunch / hail tick - Great Hail's A_Force crunch pitched up, short and quiet, a small stone tap and a faint pebble
    # scatter.  Kept quiet on purpose (no DRIVE: peak ~0.35, not normalised up) - up to 10 of these play 0.17 s apart.
    "DUALER_MENDHIT.WAV":    [("Attack/A_Force1.WAV", 0.62, 0.00, 0.26, 0.16, 1.45),
                              ("Moves/SFStep2.WAV", 0.30, 0.00, None, 0.12, 1.35),
                              ("Attack/A_Force2.WAV", 0.16, 0.03, 0.16, 0.10, 1.95)],
    "DUALER_MENDSTONE1.WAV": [("Moves/SFStep2.WAV", 1.0, 0.00, None, 0.15, 0.6),
                              ("Attack/Earth.WAV", 0.35, 0.02, 0.35, 0.2, 1.5)],
    "DUALER_MENDSTONE2.WAV": [("Moves/SFStep4.WAV", 1.0, 0.00, None, 0.15, 0.55),
                              ("Attack/Earth.WAV", 0.3, 0.40, 0.35, 0.2, 1.7)],
    # Steadfast v3 (2026-10-17, user: "okay but improve - should sound tough and appropriate for earth"): the ground
    # heaving (sub swell + slowed Earth rumble + a grinding heavy-wheel drag of rock), then ONE heavy blow as the shields
    # land - a stone-giant footfall + low crunch under a deep bronze-and-stone CLANG (bronzering at 73 Hz + a slowed parry
    # clank) - and the rubble settling with a second, lighter stomp; only a faint shimmer for the magic, no chimes.
    "DUALER_STEADFAST.WAV": [("synth:subswell:30:52:0.9", 0.55, 0.00, None, 0.2),
                             ("Attack/Earth.WAV", 0.75, 0.00, 1.5, 0.6, 0.62),
                             ("Moves/HvyWh2.WAV", 0.45, 0.08, 0.9, 0.4, 0.55),
                             ("Moves/SFStep1.WAV", 1.0, 0.62, None, 0.3, 0.5),
                             ("Attack/A_Force1.WAV", 0.6, 0.62, None, 0.3, 0.55),
                             ("synth:bronzering:73:2.2", 0.75, 0.63, None, 0.9, 1.0, 0.0, 0.0, 1.6),
                             ("Attack/Parry.WAV", 0.5, 0.63, 0.7, 0.5, 0.5),
                             ("Attack/Earth.WAV", 0.35, 0.70, 1.6, 0.8, 0.8),
                             ("Moves/SFStep3.WAV", 0.55, 1.25, None, 0.3, 0.6),
                             ("synth:shimmer:1.4", 0.12, 0.65, None, 0.0)],
    # per landing hex (sound 1, x7 - the hail landing plays cue 1 on EVERY strike hex, so it must exist): v5 only the
    # faint air rush of v3 - the shield clang moved to cue 2 (DUALER_STEADCLANG), played per SHIELDED unit by
    # patch_tc_steadfast_clang_v1.py.
    "DUALER_STEADHIT.WAV":  [("Attack/Wind.WAV", 0.05, 0.00, 0.7, 0.4, 1.3, 0.4)],
    # Steadfast v6 cue 2 (2026-10-17, user: "clang plays twice per shield - change the second one to sound a little
    # different"): the double was A_Force1's DELAYED impact (peak ~0.2 s after the clang, louder than it).  Hit 1 @0.74 s
    # = step + low crunch (A_Force1 pulled onto the clang: offset 0.08 s, cut 0.16 s) + 73 Hz bronze ring + slowed parry;
    # hit 2 @0.95 s = a lighter answering ring a fifth up (110 Hz) + brighter parry + stone tap, softer than hit 1.
    "DUALER_STEADCLANG.WAV": [("Moves/SFStep1.WAV", 0.65, 0.74, None, 0.3, 0.5),
                             ("Attack/A_Force1.WAV", 0.39, 0.70, 0.16, 0.1, 0.55, 0.0, 0.08),
                             ("synth:bronzering:73:1.6", 0.4875, 0.75, None, 0.8, 1.0, 0.0, 0.0, 1.6),
                             ("Attack/Parry.WAV", 0.325, 0.75, 0.7, 0.5, 0.5),
                             ("synth:bronzering:110:1.1", 0.30, 0.95, None, 0.6, 1.0, 0.0, 0.0, 1.6),
                             ("Attack/Parry.WAV", 0.22, 0.95, 0.6, 0.4, 0.68),
                             ("Moves/SFStep3.WAV", 0.35, 0.95, None, 0.2, 0.72)],
    # Depths of Plenty (217, Earth L2 2026-10-17): picks ringing deep in a mine, the Earth sphere's cast slowed, a low
    # earth drone, and coins clinking out at the end.
    "DUALER_DEPTHS.WAV":    [("Places/Mine.WAV", 0.8, 0.00, 2.2, 0.8, 0.85),
                             ("Attack/m_Earth.wav", 0.6, 0.05, 2.4, 0.8, 0.8),
                             ("synth:drone:65:2.4", 0.35, 0.00, None, 0.8),
                             ("Events/Gold.WAV", 0.8, 0.90, 1.4, 0.5, 0.9),
                             ("Events/Gold.WAV", 0.45, 1.35, 1.0, 0.5, 1.1)],
    # Tectonic Shift (219) v4 (2026-10-17, user: "gfx/sfx is awesome - just give it a smoother fade out"): the v3 mix
    # unchanged up to the aftershock; the tail now rolls on with the eased visual fade (fade 2.8 -> ~4.8 s, gone 5.3 s):
    # a longer aftershock + stones, a last settling of stones and a low drone, and a 2.3 s whole-mix fade (was 0.8).
    "DUALER_TECTONIC.WAV":  [("Attack/Earth.WAV", 0.34, 0.00, 1.75, 0.5, 0.80, 0.9),                   # low growl building under the hover
                             ("synth:subswell:28:44:1.7", 0.40, 0.00, None, 0.15),                     # tension rising to the split
                             ("synth:shimmer:1.9", 0.12, 0.10, None, 0.6, 1.0, 0.5),                   # subtle magic over the hovering motes
                             ("Attack/A_Force2.WAV", 0.85, 1.58, None, 0.4, 0.68),                     # the CRACK as the fissure opens
                             ("Attack/Earth.WAV", 1.00, 1.60, 2.30, 0.9, 1.00),                        # Tremors itself (gritty, natural pitch)
                             ("Attack/Earth.WAV", 0.55, 1.64, 2.30, 1.0, 0.78),                        #   a slowed double for weight
                             ("Attack/Shockw.wav", 0.45, 1.60, 1.20, 0.6, 0.72),                       # shockwave whump
                             ("xSFX/stones.wav", 0.65, 1.78, 2.00, 0.8, 0.95),                         # rocks and grit tumbling
                             ("xSFX/stones.wav", 0.40, 2.35, 2.40, 1.4, 0.78),                         #   more, deeper - v4: longer, slower fade
                             ("synth:bell:98:2.2", 0.10, 1.62, None, 1.0),                             # one low magic ring under the split
                             ("Attack/Earth.WAV", 0.40, 2.70, 2.60, 1.6, 0.70),                        # aftershock rumble - v4: rolls on through the visual fade
                             ("xSFX/stones.wav", 0.22, 3.30, 1.90, 1.3, 0.62),                         # v4: last stones settling as the fissure fades
                             ("synth:drone:45:2.6", 0.20, 2.70, None, 1.6)],                           # v4: a low drone under the fade, dying with the motes
    # Overgrowth v2 (2026-10-17, user: too recognizable - keep similar, modify): the grove no longer opens the sound -
    # it swells in REVERSED and slowed under a slowed Earth cast, then plays forward deeper (0.82x, sliced past its
    # familiar opening birds) as a bed; the Water cast pitched up a touch; EnchP02 swapped for a soft rising string
    # chord + shimmer; a faint leafy wind rustle on top - the forest creeping outward.
    # Rite of the Seas (221, Water L2 2026-10-17): a sea rite - the swell drawn in (the big-water wash REVERSED and slowed)
    # breaking into a slow deep wash, a low sung chant (choir D minor, then a fifth above), two soft ritual drum strokes,
    # a ship's bell struck twice and a faint sea wind over a sub-bass swell.
    "DUALWT_RITESEAS.WAV":  [("Moves/waterlg.WAV", 0.55, 0.00, 1.25, 0.15, -0.72, 0.35),
                             ("Moves/waterlg.WAV", 0.6, 1.05, 2.3, 1.0, 0.62, 0.25, 0.35),
                             ("synth:subswell:30:55:3.0", 0.45, 0.00, None, 0.9),
                             ("synth:choir:147:2.6:minor", 0.42, 0.30, None, 0.9, 1.0, 0.4),
                             ("synth:choir:220:1.8:minor", 0.22, 1.05, None, 0.8, 1.0, 0.4),
                             ("synth:drum:62:1.0", 0.62, 0.28, None, 0.5),
                             ("synth:drum:62:1.0", 0.52, 1.02, None, 0.5),
                             ("synth:bell:415:1.8", 0.34, 1.55, None, 0.8),
                             ("synth:bell:415:1.6", 0.26, 1.85, None, 0.8),
                             ("synth:wind:3.0", 0.12, 0.10, None, 0.9, 1.0, 0.6)],
    # Crashing Wave (220, Water L1 2026-10-17): Gust's timeline in water - the swell drawn back (the big-water wash
    # REVERSED, slowed) with a sub swell, the CRASH as the breath starts (heavy plunge + wash), the foaming surge rushing
    # forward (slowed wash, spray hiss, the Water cast under it, air pushed ahead), then a smaller slap + slosh as the
    # units are thrown back (Gust's hop ~1.6 s).
    "DUALWT_CRASHWAVE.WAV": [("Moves/waterlg.WAV", 0.6, 0.00, 0.38, 0.05, -0.85, 0.2),
                             ("synth:subswell:38:70:0.4", 0.45, 0.00, None, 0.1),
                             ("synth:splash:1.6", 0.85, 0.30, None, 0.6),
                             ("Moves/waterlg.WAV", 0.75, 0.28, 1.7, 0.8, 0.78, 0.0, 0.10),
                             ("synth:hiss:1.6", 0.55, 0.35, None, 0.6),
                             ("Attack/m_Water.WAV", 0.35, 0.25, 1.7, 0.8, 0.85),
                             ("synth:wind:1.7", 0.18, 0.30, None, 0.8, 1.0, 0.3),
                             ("synth:splash:0.9", 0.45, 1.58, None, 0.4),
                             ("Moves/M_Swim1.WAV", 0.35, 1.62, None, 0.3, 0.8)],
    # Flash Flood (223, Water L4 2026-10-17): a deep rising groan (sub swell + Tremors' rumble slowed far down, quiet), two
    # layers of slowed rushing water building through the hover of the flood, the Water cast slowed under a soft hiss,
    # then the surge as the flood hits (~2.4-3.1 s = kind-29 ticks 84-104): two synth splashes, slaps and a slowed swim
    # plunge, and the water draining away.
    "DUALWT_FLASHFLOOD.WAV": [("synth:subswell:32:58:3.0", 0.55, 0.00, None, 0.8),
                             ("Attack/Earth.WAV", 0.40, 0.05, 3.0, 0.9, 0.55),
                             ("Moves/waterlg.WAV", 0.85, 0.00, 3.4, 1.0, 0.62, 0.6),
                             ("Moves/waterlg.WAV", 0.75, 0.10, 1.45, 0.45, 1.08, 0.25),       # v2: the flood front rushing in (visual sweep ticks 4-52)
                             ("synth:wind:1.6", 0.22, 0.05, None, 0.5),                      # v2: the air shoved ahead of the wall of water
                             ("Moves/waterlg.WAV", 0.55, 0.45, 3.2, 1.0, 0.78, 0.5, 0.3),
                             ("synth:hiss:3.2", 0.22, 0.20, None, 0.6),
                             ("Attack/m_Water.WAV", 0.45, 0.15, 2.2, 0.8, 0.7),
                             ("synth:splash:1.4", 0.9, 2.40, None, 0.3),
                             ("Moves/SlimeS1.WAV", 0.5, 2.50, None, 0.2, 0.8),
                             ("Moves/M_Swim1.WAV", 0.6, 2.56, None, 0.3, 0.75),
                             ("Moves/SlimeS3.WAV", 0.45, 2.70, None, 0.2, 0.7),
                             ("synth:splash:1.2", 0.55, 2.85, None, 0.3),
                             ("Moves/SlimeS2.WAV", 0.35, 3.05, None, 0.2, 0.9),
                             ("Moves/waterlg.WAV", 0.5, 3.00, 1.5, 0.9, 0.9)],
    # Summon Sea Serpent (222, Water L3 2026-10-17): the sea drawing back (reversed slowed wash) over a deep sub swell,
    # the serpent BREACHING (heavy splash + slowed churning swim), then its long hiss over a low throat-growl and a deep
    # slowed breath, and the wash settling.  3.3 s.
    "DUALWT_SERPENT.WAV":   [("Moves/waterlg.WAV", 0.55, 0.00, 1.0, 0.1, -0.72, 0.3),
                             ("synth:subswell:34:58:1.3", 0.6, 0.00, None, 0.3),
                             ("synth:splash:1.0", 0.85, 0.95, None, 0.0),
                             ("Moves/M_Swim1.WAV", 0.5, 1.00, 1.2, 0.5, 0.62),
                             ("Attack/A_Monst2.WAV", 0.32, 1.15, 1.3, 0.6, 0.5),
                             ("synth:hiss:1.5", 0.5, 1.20, None, 0.0),
                             ("Attack/DBreath.WAV", 0.22, 1.25, 1.1, 0.6, 0.55, 0.15),
                             ("Moves/waterlg.WAV", 0.45, 1.70, 1.6, 0.8, 0.8, 0.0, 0.4)],
    # Wall of Flames (226, Fire L3 2026-10-17): the air SUCKED in toward the ring (a reversed, slowed flame burst over
    # a rising sub swell), then the IGNITION - a deep, slowed fire-start whoomp with a low thump - and the wall of fire
    # ROARING up: the fire loop slowed and darkened under a gusting updraft, crackle on top, settling away over ~2 s.
    "DUALFI_WALLFLAMES.WAV": [("Attack/FlameA.WAV", 0.55, 0.00, 0.55, 0.05, -0.62, 0.25),
                             ("synth:subswell:34:58:0.55", 0.55, 0.00, None, 0.0),
                             ("Attack/FireStrt.WAV", 0.95, 0.50, 1.3, 0.6, 0.72),
                             ("Attack/Firebs.WAV", 0.55, 0.52, 0.9, 0.5, 0.6),
                             ("Attack/Fireloop.WAV", 0.75, 0.62, 2.0, 1.0, 0.7, 0.25),
                             ("synth:wind:2.2", 0.30, 0.55, None, 0.8, 1.0, 0.3),
                             ("Attack/FlameA.WAV", 0.30, 0.95, 1.2, 0.6, 1.25, 0.1)],
    # per landing hex (sound 1 - REQUIRED: the hail landing plays it on every strike hex): a short soft FWOOSH of a
    # hex catching fire (FlameA quick and high, sliced past its attack, + a breath of hiss); quiet because it repeats x7.
    "DUALFI_FLAMEHIT.WAV":  [("Attack/FlameA.WAV", 0.22, 0.00, 0.45, 0.3, 1.35, 0.03, 0.05),
                             ("synth:hiss:0.4", 0.06, 0.00, None, 0.2)],
    # Smokescreen (225, Fire L2 2026-10-17) v2 (user: "not bad, but add fire and/or crackling/burning sound"): v1 kept -
    # the smoke drawn in (vapour hiss REVERSED, slowed), a muffled slowed FireStrt whump as it ignites, billowing smoke
    # (slowed vapour roll + gusting wind + sub swell) with embers crackling - plus a slowed burning ROAR under the bank
    # (Fireloop, sliced past its attack), a low flame whoosh at the ignition and a second, denser crackle bed.
    "DUALFR_SMOKESCREEN.WAV": [("Attack/Vapor.wav", 0.55, 0.00, 0.9, 0.15, -0.7, 0.3),
                               ("Attack/FireStrt.WAV", 0.45, 0.28, 0.7, 0.45, 0.55, 0.02),
                               ("synth:subswell:30:50:2.2", 0.45, 0.20, None, 0.9),
                               ("Attack/Vapor.wav", 0.55, 0.32, 1.9, 1.1, 0.72, 0.12),
                               ("synth:wind:2.4", 1.0, 0.25, None, 1.0),
                               ("synth:crackle:16:2.2", 0.45, 0.35, None, 0.8),
                               ("Attack/Fireloop.WAV", 1.0, 0.30, 2.3, 1.0, 0.78, 0.35, 0.4),
                               ("Attack/FlameA.WAV", 0.6, 0.22, 0.6, 0.3, 0.7, 0.05),
                               ("synth:crackle:30:2.4", 0.7, 0.45, None, 0.9)],
    # Pyroclasm (227, Fire tier 4, 2026-10-17): a volcano waking - the earth's slowed rumble over a sub-bass groan and the
    # Fire sphere's cast slowed, a REVERSED flame whoosh drawing in to a slowed eruption boom at ~1.1 s, a slowed fire
    # roar of the lava under a second deeper rumble, falling scree (rattle) and a low drone; fades out over 0.9 s.
    "DUALFR_PYROCLASM.WAV": [("Attack/Earth.WAV", 0.85, 0.00, 3.4, 1.0, 0.55),
                             ("synth:subswell:28:50:3.6", 0.6, 0.00, None, 0.9),
                             ("Attack/FlameA.WAV", 0.45, 0.35, 0.8, 0.3, -0.8, 0.3),
                             ("Attack/Explod1.wav", 0.75, 1.05, None, 0.6, 0.55),
                             ("Attack/Fireloop.WAV", 0.5, 0.90, 2.8, 1.0, 0.62, 0.5),
                             ("Attack/m_Fire.wav", 0.35, 0.15, 2.4, 0.8, 0.72),
                             ("synth:rattle:24:14:2.2", 0.3, 1.25, None, 0.9),
                             ("Attack/Earth.WAV", 0.45, 1.50, 2.2, 0.9, 0.8, 0.2),
                             ("synth:drone:55:3.8", 0.28, 0.00, None, 1.0)],
    # Magic Missile v15 (2026-10-18, user: "still some echo / separate tinny quiet noise; add the slower tail"): the
    # 1.5-speed Magic Bolt copy (the tinny ghost) is gone; a slower, quieter Magic Bolt (0.65) carries a long tail
    # under the 0.82 bass layer; long fades throughout.
    "DUALCO_MMISSILE.WAV":  [("Attack/Ice.WAV", 0.70, 0.00, 0.26, 0.12, 0.90),
                             ("Attack/MagicA04.WAV", 0.85, 0.00, None, 0.45, 1.0),
                             ("Attack/MagicA04.WAV", 0.45, 0.00, None, 0.50, 0.82),
                             ("Attack/MagicA04.WAV", 0.30, 0.05, None, 0.70, 0.65),
                             ("synth:airwhoosh:1800:4500:0.60", 0.14, 0.00, None, 0.35)],
    # per landing (cue 1, x3) v15: a soft, warm magic thud - a short Magic Bolt slice (0.9) with a gentle Enchant
    # Weapon touch; no shimmer / high layers (user heard a tinny ghost); quiet, no drive.
    "DUALCO_MMHIT.WAV":     [("Attack/MagicA04.WAV", 0.35, 0.00, 0.35, 0.20, 0.9),
                             ("Attack/Magic05.WAV", 0.18, 0.00, 0.40, 0.30, 1.3)],
    # Royal Ambition v9 (2026-10-18, user: "don't like it, especially the drum. improve it"): the Herald & Choir idea
    # without any drum; warmer herald call (top octave dropped, low octave up), choir + strings blended as one warm
    # D-major bed, bell tolls softened, sparkle bells + shimmer on top.  DRIVE 1.4 (gentle; RMS ~0.21 like City Spy).
    "DUALCO_ROYAL.WAV":     [('synth:horn:293.66:293.66:0.40', 0.62, 0.00, 0.14, 0.05),
                             ('synth:horn:146.83:146.83:0.40', 0.34, 0.00, 0.14, 0.05),
                             ('synth:horn:587.33:587.33:0.40', 0.07, 0.00, 0.14, 0.05),
                             ('synth:horn:293.66:293.66:0.40', 0.62, 0.17, 0.10, 0.04),
                             ('synth:horn:146.83:146.83:0.40', 0.34, 0.17, 0.10, 0.04),
                             ('synth:horn:587.33:587.33:0.40', 0.07, 0.17, 0.10, 0.04),
                             ('synth:horn:440.00:440.00:0.90', 0.70, 0.30, 0.66, 0.36),
                             ('synth:horn:220.00:220.00:0.90', 0.38, 0.30, 0.66, 0.36),
                             ('synth:strings:146.83:2.3', 0.40, 0.86, None, 1.10, 1.00, 0.35),
                             ('synth:strings:293.66:2.2', 0.22, 0.90, None, 1.10, 1.00, 0.35),
                             ('synth:choir:146.83:2.1', 0.56, 0.95, None, 1.10),
                             ('synth:choir:220.00:2.0', 0.26, 0.98, None, 1.10),
                             ('synth:choir:293.66:2.0', 0.24, 1.00, None, 1.10),
                             ('synth:bell:146.83:2.2', 0.12, 0.95, None, 1.20),
                             ('synth:bell:220.00:1.6', 0.10, 1.65, None, 1.00),
                             ('synth:shimmer:1.8', 0.26, 1.10, None, 0.90, 1.00, 0.30),
                             ('synth:bell:1174.66:1.0', 0.16, 1.35, None, 0.70),
                             ('synth:bell:1479.98:1.0', 0.14, 1.50, None, 0.70),
                             ('synth:bell:1760.00:1.0', 0.13, 1.65, None, 0.70),
                             ('synth:bell:2349.32:1.0', 0.11, 1.80, None, 0.70)],
    # City Spy v3 (2026-10-18, user: "the sfx needs a smoother fade out"): v2's layers and timing; the Charm whispers,
    # bells, glass wind, shimmer and drone all decay over ~1.2-1.5 s with gentler fade curves (fpow < 1 keeps the tail
    # audible a little longer, then it melts away); whole-mix fade-out 0.7 -> 1.4 s.  3.0 s (v2 2.5 s).
    "DUALCO_CITYSPY.WAV":   [("Attack/Magic07.WAV", 0.5, 0.00, 1.1, 0.6, -0.8, 0.3),
                             ("synth:glasswind:330:520:1.6", 0.35, 0.05, None, 0.9),
                             ("synth:shimmer:2.0", 0.40, 0.30, None, 1.1),
                             ("Attack/EnchP02.WAV", 0.35, 0.95, 1.4, 1.0, 0.72, 0.0, 0.0, 0.7),
                             ("synth:bell:784:1.8", 0.18, 1.05, None, 1.2),
                             ("synth:bell:1175:1.6", 0.10, 1.30, None, 1.1),
                             ("synth:drone:110:3.0", 0.25, 0.00, None, 1.5),
                             ("Attack/Charm.WAV", 0.55, 0.55, 2.3, 1.5, 0.94, 0.25, 0.65, 0.6)],
    # Essence Shift (231, Cosmos L4 2026-10-17): the node's essence drawn inward (a magical vacuum + rising sub swell,
    # 0-0.85 s, the swirl converging), then a deep resonant SHIFT at the convergence (two low bells a fifth apart + a
    # low choir) with a slowed enchantment shimmer and a cosmic sparkle bed over a soft drone, ringing out with the
    # starlight ring.  3.45 s.
    "DUALCO_ESSENCE.WAV":   [("synth:vacuum:0.85", 0.45, 0.00, None, 0.1),
                             ("synth:subswell:40:58:0.9", 0.5, 0.00, None, 0.1),
                             ("synth:bell:73:2.6", 0.6, 0.85, None, 1.0),
                             ("synth:bell:110:2.2", 0.3, 0.86, None, 0.9),
                             ("synth:choir:146.8:2.0", 0.3, 0.80, None, 1.0),
                             ("synth:shimmer:2.6", 0.4, 0.10, None, 0.6),
                             ("synth:drone:55:3.2", 0.35, 0.00, None, 1.0),
                             ("Attack/EnchP02.WAV", 0.3, 0.85, 1.8, 0.8, 0.6)],
    # Reversal (234, Secret L3 2026-10-18): a MIRRORED whoosh - the wind drawn IN reversed and slowed while an airy band
    # sweeps up, meeting at a soft crossing chime, then the same wind thrown back OUT forward while the band sweeps down
    # (the swap); a faint sub swell under it and a shimmer as the stats settle.
    "DUALSE_REVERSAL.WAV":  [("Attack/Wind.WAV", 0.60, 0.00, 0.62, 0.10, -1.15, 0.25),
                             ("synth:airwhoosh:900:5200:0.62", 0.38, 0.00, None, 0.08),
                             ("Attack/Wind.WAV", 0.60, 0.60, 0.75, 0.40, 1.15, 0.03),
                             ("synth:airwhoosh:5200:900:0.75", 0.38, 0.60, None, 0.35),
                             ("synth:bell:784:1.2", 0.22, 0.56, None, 0.60),
                             ("synth:bell:1175:1.0", 0.12, 0.60, None, 0.55),
                             ("synth:subswell:45:70:1.4", 0.30, 0.00, None, 0.50),
                             ("synth:shimmer:0.9", 0.20, 0.70, None, 0.50)],
    # Lucky v3 (2026-10-18, user: "not bad but needs polish, smoothed out - feels janky"): the same rising plucked-harp
    # arpeggio (E5 G5 B5 E6) now LEGATO - soft 22 ms pluck attacks, notes 85 ms apart each ringing 2.2 s with slow fades -
    # with two soft echoes (190 / 380 ms) as a reverb tail, a quieter coin ting, a long shimmer and the EnchP01 chime.
    "DUALSE_LUCKY.WAV":     [("synth:harp:659:2.2", 0.44, 0.000, None, 1.4, 1.0, 0.022, 0.0, 0.55),
                             ("synth:harp:784:2.2", 0.42, 0.085, None, 1.4, 1.0, 0.022, 0.0, 0.55),
                             ("synth:harp:988:2.2", 0.40, 0.170, None, 1.4, 1.0, 0.022, 0.0, 0.55),
                             ("synth:harp:1319:2.2", 0.37, 0.255, None, 1.4, 1.0, 0.022, 0.0, 0.55),
                             ("synth:harp:659:2.2", 0.097, 0.190, None, 1.4, 1.0, 0.02, 0.0, 0.55),
                             ("synth:harp:784:2.2", 0.092, 0.275, None, 1.4, 1.0, 0.02, 0.0, 0.55),
                             ("synth:harp:988:2.2", 0.088, 0.360, None, 1.4, 1.0, 0.02, 0.0, 0.55),
                             ("synth:harp:1319:2.2", 0.081, 0.445, None, 1.4, 1.0, 0.02, 0.0, 0.55),
                             ("synth:harp:659:2.2", 0.040, 0.380, None, 1.4, 1.0, 0.03, 0.0, 0.55),
                             ("synth:harp:784:2.2", 0.038, 0.465, None, 1.4, 1.0, 0.03, 0.0, 0.55),
                             ("synth:harp:988:2.2", 0.036, 0.550, None, 1.4, 1.0, 0.03, 0.0, 0.55),
                             ("synth:harp:1319:2.2", 0.033, 0.635, None, 1.4, 1.0, 0.03, 0.0, 0.55),
                             ("Events/Gold.WAV", 0.12, 0.30, 0.40, 0.30, 1.2, 0.012, 0.05, 0.6),
                             ("synth:shimmer:1.8", 0.16, 0.08, None, 1.1, 1.0, 0.25, 0.0, 0.6),
                             ("Attack/EnchP01.WAV", 0.22, 0.02, 1.4, 0.9, 1.1, 0.03, 0.0, 0.6)],
    # Transmutation (235, Secret L4 2026-10-18): slowed slime bubbles = an alembic bubbling over a sub swell, then a
    # cascade of coins (Gold.WAV sliced at 3 offsets and pitched up, so the stock pickup is not recognisable) with rising
    # tine pings, a struck bell as the metal turns, and a magical shimmer over it all.
    "DUALSE_TRANSMUTE.WAV": [("Moves/SlimeS1.WAV", 0.55, 0.00, None, 0.15, 0.55),
                             ("Moves/SlimeS3.WAV", 0.45, 0.22, None, 0.12, 0.62),
                             ("Moves/SlimeS2.WAV", 0.45, 0.40, None, 0.10, 0.70),
                             ("Moves/SlimeS4.WAV", 0.40, 0.55, None, 0.10, 0.80),
                             ("Moves/SlimeS1.WAV", 0.35, 0.70, None, 0.15, 0.95),
                             ("synth:subswell:55:90:1.2", 0.25, 0.00, None, 0.40),
                             ("Events/Gold.WAV", 0.55, 0.85, 0.45, 0.20, 1.22, 0.0, 0.10),
                             ("Events/Gold.WAV", 0.45, 1.00, 0.45, 0.25, 1.48, 0.0, 0.35),
                             ("Events/Gold.WAV", 0.38, 1.18, 0.55, 0.35, 1.80, 0.0, 0.60),
                             ("synth:tine:2349:0.5", 0.20, 0.88, None, 0.20),
                             ("synth:tine:2794:0.5", 0.18, 0.98, None, 0.20),
                             ("synth:tine:3136:0.5", 0.16, 1.10, None, 0.20),
                             ("synth:tine:3520:0.6", 0.15, 1.24, None, 0.25),
                             ("synth:bell:1047:1.4", 0.20, 0.82, None, 0.60),
                             ("synth:shimmer:1.6", 0.30, 0.45, None, 0.50)],
    # Mimic (233, Secret L2 2026-10-18): a MIRRORED chime swell - the enchantment chime reversed + slowed (with Dispel
    # Magic's own cast reversed under it) sucked in up to a struck E5/E6 'mirror line', then the same chime thrown back
    # forward and higher = its reflection; airy bands rising then falling around the line, a shimmer over it all.
    "DUALSE_MIMIC.WAV":     [("Attack/EnchP01.WAV", 0.70, 0.00, 0.85, 0.04, -0.82, 0.30),     # the chime REVERSED + slowed = a swell sucked in
                             ("Attack/MAGIC13.WAV", 0.30, 0.10, 0.70, 0.05, -0.70, 0.25),     # Dispel's own cast reversed under it (the fallback's root)
                             ("synth:glasswind:900:2600:0.80", 0.16, 0.05, None, 0.10),        # an airy band rising to the mirror line
                             ("synth:bell:659:1.3", 0.26, 0.82, None, 0.70),                   # the mirror line: E5 + its octave struck together
                             ("synth:bell:1318:1.0", 0.14, 0.83, None, 0.60),
                             ("Attack/EnchP01.WAV", 0.42, 0.86, 0.80, 0.45, 1.22),            # ... and the chime thrown back FORWARD, higher = the reflection
                             ("synth:glasswind:2600:900:0.80", 0.12, 0.88, None, 0.40),
                             ("synth:shimmer:1.6", 0.20, 0.40, None, 0.70)],
    # Seeker Bolts v4 (2026-10-18; user on v3: 'add a bit of the original PROJECTILE sound, but only very subtly'): the
    # original record-68 shot cue (Zu/HOLYSPIRITDEATH, played at the shot before the rework) now sits ONLY under the
    # launch (the moment the bolt flies), longer (1.6 s, its shimmering tail rings on past the launch) at ~14 % of the
    # launch energy - in v3 it was cut at 0.8 s, ~8 % and masked.  Removed from the charge (it blurred the build-up).
    # The hit keeps the original impact cue (DREAM_ESSENCE_CORPSE_COLLECT).  No bell / tine / chime layers, no DRIVE.
    # cue 0 = the unit's attack animation = the start of the 30-tick (~0.87 s) orb spin-up: the vanilla VORTEX swirl
    # sped up (the orbs whirling) under a warm rising tone with an accelerating orbit tremolo, and the Magic Bolt sound
    # (MAGICA04) played BACKWARDS so it swells into the launch.
    "SEEKER_CHARGE.WAV":    [("synth:seekcharge2:98:294:0.90", 0.95, 0.00, None, 0.0),
                             ("Attack/Vortex.WAV", 0.85, 0.00, 0.90, 0.10, 1.35, 0.55, 0.40),
                             ("Attack/MagicA04.WAV", 0.75, 0.32, 0.58, 0.0, -1.0)],
    # cue 2 (patch_tc_seekerbolts, the release tick): a deep SHOCKWAVE whoomp (vanilla SHOCKW onset), the Magic Bolt zap
    # (MAGICA04) for identity, an A_FORCE2 punch, the v1 thump/blast/zap synth, a short electric crackle and the
    # original projectile sound faintly underneath.
    "SEEKER_LAUNCH.WAV":    [("synth:seeklaunch:0.8", 0.75, 0.00, None, 0.1),
                             ("Attack/Shockw.wav", 0.55, 0.00, 0.75, 0.45, 1.25),
                             ("Attack/MagicA04.WAV", 0.85, 0.00, 0.80, 0.35, 1.0),
                             ("Attack/A_Force2.WAV", 0.40, 0.00, 0.24, 0.10, 1.0),
                             ("synth:seekzap:0.35:3771", 0.30, 0.01, None, 0.10),
                             ("Zu/HOLYSPIRITDEATH.WAV", 0.55, 0.00, 1.60, 0.90, 1.0)],
    # cue 1 (each landing, vanilla 0x42A0C6): a rich EXPLOSION (vanilla EXPLOD1, slightly higher) with the deep boom
    # synth under it, an A_FORCE1 body hit, a crackle of blue sparks and the original impact cue.
    "SEEKER_HIT.WAV":       [("Attack/Explod1.wav", 0.70, 0.00, 0.90, 0.50, 1.15),
                             ("synth:seekhit:0.6", 0.75, 0.00, None, 0.1),
                             ("Attack/A_Force1.WAV", 0.45, 0.00, 0.40, 0.20, 0.95),
                             ("synth:seekzap:0.45:3772", 0.28, 0.02, None, 0.15),
                             ("selecte from hk/DREAM_ESSENCE_CORPSE_COLLECT.WAV", 1.6, 0.00, 0.90, 0.40)],
    # Tame Animal v2 (ability 0xC9, 2026-10-18; user: own sfx): a low wary growl (vanilla MONSTER1 slowed) easing into a
    # contented purr (new 'purr' synth), a soft slowed CHARM shimmer at low gain, the Earth sphere's cast for nature and a
    # short sub swell.  No bell / tine layers, no DRIVE.
    "TAME_ANIMAL.WAV":      [("Attack/Monster1.WAV", 0.40, 0.00, 0.70, 0.45, 0.78),
                             ("synth:purr:27:2.0", 0.95, 0.35, None, 0.6, 1.0, 0.35),
                             ("Attack/Charm.WAV", 0.22, 0.10, 2.0, 0.8, 0.80, 0.30),
                             ("Attack/m_Earth.wav", 0.32, 0.00, 2.2, 0.9, 1.05, 0.15),
                             ("synth:subswell:55:70:0.6", 0.25, 0.0, None, 0.3)],
    # Hurl Skull v5 landing (cue 1; 2026-10-19 user: 'more of a CRUNCH, layer some CRACKLING into the explosion, as
    # violent as Self-Destruct'): the CRUNCH first and loudest at t=0 - the boulder's A_PUNCH2 pitched down hard, the
    # D_UNDEAD bone break, a rock/bone splinter (stones), Kain's MACE impact and an A_FORCE1 thud; 15 ms later the
    # Self-Destruct BLAST at full weight (pitched 0.92) doubled by Kain's EXPLODE (0.85, darker) and Fire Ball's Explod1
    # for the hot crack, a sub boom, and a burst of FIRE CRACKLE (dense popping embers + Kain's BURN roar) riding the
    # tail.  Heavy drive.  No shriek, no bells.
    "SKULL_HIT.WAV":    [("Attack/A_Punch2.WAV", 1.25, 0.00, None, 0.05, 0.78),
                         ("Hit_Death/D_Undead.WAV", 1.0, 0.00, 0.40, 0.15, 0.88),
                         ("xSFX/stones.wav", 0.75, 0.00, 0.45, 0.20, 1.10),
                         ("Kain/MACE.wav", 0.8, 0.00, 0.35, 0.15, 0.80),
                         ("Attack/A_Force1.WAV", 0.75, 0.00, None, 0.1, 0.70),
                         ("Attack/A_Punch1.WAV", 1.10, 0.025, None, 0.08, 0.62),        # v8 (user: 'layer in an added CRUNCH, more heavy'): a second, deeper punch 25 ms after the first
                         ("xSFX/stones.wav", 0.95, 0.030, 0.55, 0.25, 0.68),            # v8: low gravel / bone grind, pitched well down
                         ("Hit_Death/D_WoodLG.WAV", 0.55, 0.020, 0.45, 0.20, 0.72),     # v8: a splintering crack under it
                         ("Attack/BLAST.WAV", 1.0, 0.015, 2.2, 0.9, 0.92),
                         ("Kain/EXPLODE.wav", 0.75, 0.02, 1.9, 0.8, 0.85),
                         ("Attack/Explod1.wav", 0.5, 0.015, 1.3, 0.6, 1.06),
                         ("synth:crackle:70:1.9", 0.55, 0.10, None, 0.6),
                         ("Kain/BURN.wav", 0.45, 0.15, 1.8, 0.8, 0.9, 0.15),
                         ("synth:subswell:36:46:1.2", 0.55, 0.00, None, 0.8)],
    # Hurl Skull v5 flight (cue 2, fired by patch_bxl_ranged_abilities_v5 at the 2nd path point = right after the
    # throw; replaces the scream): an evil, epic DEATHFIRE roar that builds into the impact - a flame swoosh (Kain's
    # FLAMESW pitched down) over a rolling fire roar (Fireloop's body), a low demonic growl (Kain's GROWL1 at 0.66),
    # a dark choir swelling underneath (Kain's CHOIR2 at 0.72), a rising
    # sub-bass swell and an airy whoosh rising in pitch - the swoosh / roar / growl hit at once (0.02-0.06 s fade-ins),
    # the whole thing grows louder toward ~1.2 s and dies over the last 0.25 s.  No screams, no bells.
    "SKULL_FLIGHT.WAV": [("Kain/FLAMESW.wav", 1.0, 0.00, 1.45, 0.35, 0.78, 0.02),
                         ("Attack/Fireloop.WAV", 0.7, 0.00, 1.45, 0.30, 0.85, 0.05, 0.6),
                         ("Kain/GROWL1.wav", 0.55, 0.00, 1.35, 0.35, 0.66, 0.06),
                         ("Kain/CHOIR2.wav", 0.45, 0.00, 1.45, 0.40, 0.72, 0.15),
                         ("synth:subswell:28:52:1.45", 0.55, 0.00, None, 0.25),
                         ("synth:airwhoosh:400:1600:1.45", 0.30, 0.00, None, 0.2)],
    "DUALEW_OVERGROWTH.WAV": [("Places/SGrove.WAV", 0.55, 0.00, 1.1, 0.25, -0.9, 0.5),
                             ("Attack/m_Earth.wav", 0.55, 0.05, 2.6, 0.8, 0.86),
                             ("Places/SGrove.WAV", 0.75, 0.75, 2.4, 1.0, 0.82, 0.35, 1.2),
                             ("Attack/m_Water.WAV", 0.38, 0.45, 2.2, 0.8, 1.12, 0.1),
                             ("synth:strings:174.6:2.4", 0.22, 0.55, None, 0.9, 1.0, 0.5),
                             ("synth:shimmer:2.0", 0.18, 0.90, None, 0.8),
                             ("synth:wind:3.0", 0.22, 0.20, None, 0.9)],
    "DUALEL_GOLDENAGE.WAV": [("Events/Gold.WAV", 1.0, 0.00, 1.6, 0.5),                          # coins
                             ("Attack/EnchP02.WAV", 0.7, 0.10, 1.8, 0.6, 0.9),                 # warm enchantment shimmer
                             ("Events/Gold.WAV", 0.5, 0.55, 1.2, 0.5, 1.15)],                  # a second, brighter clink
    "DUALFA_IMPLOHIT.WAV":  [("Attack/Shockc.WAV", 0.8, 0.00, None, 0.4),                      # cue 1 = the landing: the collapse crack
                             ("Attack/Explod1.wav", 0.7, 0.04, None, 0.5, 0.8, 0.0),           # a deep thud
                             ("Attack/FireStrt.WAV", 0.4, 0.10, 1.0, 0.5)],
    # v2 (user: a WAR CRY): a massed shout - the monster roars layered as a throaty yell, the charge horn under it
    # v4 (user: horn LOUDER, then swords clashing like the Arena sound, punctuated by a magical buff)
    # v5 (user: horn + swords SIMULTANEOUS; the magic part = Fury's fire sound, not the roar, playing as the crossed
    # swords appear): Fury = Spells.pfs record 43 [FIRESTRT, [A_MONST2]].  The swords' gfx = 2 falling swords x 3
    # frames x 2 ticks (~80 ms/frame at ~25 ticks/s) -> the crossed swords appear ~0.48 s in.
    "DUALFA_FRENZY.WAV":    [("Attack/CallHero.wav", 1.0, 0.00, 1.5, 0.4, 0.80, 0.0),          # the horn (loudest layer)
                             ("Places/Arena.wav", 0.55, 0.00, 1.3, 0.4),                       # the arena clash, under the horn
                             ("Attack/A_Sword1.WAV", 0.45, 0.08, None, 0.2),
                             ("Attack/Parry.WAV", 0.4, 0.28, None, 0.2),
                             ("Attack/A_Sword3.WAV", 0.35, 0.62, None, 0.2),
                             ("Attack/FireStrt.WAV", 0.85, 0.96, 1.4, 0.5)],     # v7: 3 swords x 4 frames x 80 ms -> the cross at 0.96 s     # v6: 3 falling swords x 3 frames x 80 ms -> the cross at 0.72 s                   # Fury's fire as the crossed swords appear
    "DUALFA_DROUGHTP.WAV":  [("Attack/FireStrt.WAV", 0.8, 0.00, 1.2, 0.5, 1.15, 0.0)],       # cue 1: a short dry crackle, replayed ~40x by the map-wide twinkle (Water Mastery = WATERLG)
    "DUALFA_DROUGHT.WAV":   [("Attack/Windloop.WAV", 0.9, 0.00, 2.8, 1.0, 0.9, 0.3),           # a long dry wind
                             ("Attack/FireStrt.WAV", 0.4, 0.60, 1.6, 0.8, 0.8, 0.2),           # crackle of parched ground
                             ("Attack/Earth.WAV", 0.3, 0.20, 1.5, 0.8, 0.7, 0.2)],
    "DUALEF_FORGEBLAST.WAV": [("Attack/Explod1.wav", 1.0, 0.00, None, 0.4),
                             ("Kain/EXPLODE.wav", 0.85, 0.02, None, 0.5, 0.8, 0.0),
                             ("Attack/Shockw.wav", 0.8, 0.05, None, 0.5),
                             ("Kain/MACE.wav", 0.7, 0.00, None, 0.2),
                             ("Attack/FireStrt.WAV", 0.7, 0.10, None, 0.4),
                             ("Kain/FLAMESW2.wav", 0.6, 0.15, None, 0.3),
                             ("Kain/BURN.wav", 0.6, 0.40, 2.0, 0.6),
                             ("Attack/DBreath.WAV", 0.4, 0.10, 1.6, 0.7, 0.8, 0.0)],
    "DUALEF_ARMSRACE.WAV":  [("Kain/MACE.wav", 0.8, 0.00, None, 0.2),                       # hammering rhythm
                             ("Kain/MACE.wav", 0.75, 0.32, None, 0.2, 1.08, 0.0),
                             ("Kain/MACE.wav", 0.8, 0.64, None, 0.2, 0.96, 0.0),
                             ("Kain/MACE.wav", 0.7, 0.96, None, 0.2, 1.04, 0.0),
                             ("Attack/Fireloop.WAV", 0.45, 0.00, 2.0, 0.7, 1.0, 0.0),       # forge fire under it
                             ("Attack/EnchP03.WAV", 0.6, 0.20, None, 0.4),                  # the enchantment chime
                             ("synth:shimmer:2.2", 0.35, 0.10, None, 0.0),
                             ("synth:drone:110:2.0", 0.25, 0.30, None, 0.0)],
    "DUALDF_STARHIT1.WAV":  [("Attack/A_Force1.WAV", 0.8, 0.00, None, 0.0),
                             ("Attack/Lightng.WAV", 0.9, 0.00, 0.7, 0.3),
                             ("Attack/TurnUnd.WAV", 0.9, 0.00, 0.9, 0.4),
                             ("Attack/EnchP02.WAV", 0.5, 0.05, 1.2, 0.5)],
    "DUALDF_STARHIT2.WAV":  [("Attack/A_Force1.WAV", 0.8, 0.00, None, 0.0, 0.94),
                             ("Attack/Lightng.WAV", 0.9, 0.00, 0.7, 0.3, 1.1),
                             ("Attack/TurnUnd.WAV", 0.9, 0.00, 0.9, 0.4, 1.12),
                             ("Attack/EnchP03.WAV", 0.5, 0.05, 1.2, 0.5)],
}
OLD_FILES = ["DUALEA_BOULDERHIT.WAV", "DUALDF_HFHIT.WAV", "DUALAD_SUFFHIT.WAV"]          # earlier outputs no longer referenced - removed on --apply/--revert
# per-file drive: the mix is pushed through a soft clipper (tanh) before normalising, so the quieter layers come
# up without the stab clipping - Bloodbath was "too quiet" at plain peak normalisation
LOOP_RISE = 1.45                                          # s: silence -> full volume = the 50-tick stone delay
FADE_OUT = {"SKULL_HIT.WAV": 0.7, "SKULL_FLIGHT.WAV": 0.25, "TAME_ANIMAL.WAV": 0.6, "SEEKER_CHARGE.WAV": 0.03, "SEEKER_LAUNCH.WAV": 0.6, "SEEKER_HIT.WAV": 0.3, "DUALSE_MIMIC.WAV": 0.6, "DUALSE_LUCKY.WAV": 1.0, "DUALSE_TRANSMUTE.WAV": 0.6, "DUALSE_REVERSAL.WAV": 0.5, "DUALCO_ESSENCE.WAV": 0.8, "DUALCO_CITYSPY.WAV": 1.4, "DUALCO_ROYAL.WAV": 0.9, "DUALCO_MMISSILE.WAV": 0.5, "DUALCO_MMHIT.WAV": 0.25, "DUALFR_PYROCLASM.WAV": 0.9, "DUALFR_SMOKESCREEN.WAV": 0.8, "DUALFI_WALLFLAMES.WAV": 0.7, "DUALWT_SERPENT.WAV": 0.7, "DUALWT_FLASHFLOOD.WAV": 0.9, "DUALWT_CRASHWAVE.WAV": 0.6, "DUALWT_RITESEAS.WAV": 0.9, "DUALER_STEADCLANG.WAV": 0.5, "DUALEW_OVERGROWTH.WAV": 0.8, "DUALLW_WORLDHEALER.WAV": 0.9, "DUALER_STEADFAST.WAV": 0.9, "DUALER_MENDWALLS.WAV": 0.5, "DUALER_TECTONIC.WAV": 2.3, "DUALAI_CROSSWIND.WAV": 1.6, "DUALAI_STATICSHIELD.WAV": 0.8, "DUALDE_WITHER.WAV": 0.9, "DUALDE_CALLDEAD.WAV": 1.5, "DUALDF_REPENT.WAV": 1.2, "DUALDF_REPHIT.WAV": 1.6, "DUALLI_MIRACLE.WAV": 1.2, "DUALAD_BANSHEE.WAV": 3.5, "DUALAD_SUFFOCATE.WAV": 1.2}   # whole-mix fade-out to silence (2026-10-16; Banshee ended too suddenly)
FADE_IN = {"DUALDF_HFLOOP.WAV": LOOP_RISE, "DUALDF_REPENT.WAV": 0.3, "DUALDF_HARVEST.WAV": 0.25, "DUALDF_STARLOOP.WAV": 0.3}   # whole-mix fade-in (applied after the drive)
DRIVE = {"SKULL_HIT.WAV": 2.6, "SKULL_FLIGHT.WAV": 1.7, "DUALSE_MIMIC.WAV": 1.15, "DUALSE_LUCKY.WAV": 1.2, "DUALSE_TRANSMUTE.WAV": 1.8, "DUALSE_REVERSAL.WAV": 1.1, "DUALCO_ESSENCE.WAV": 1.3, "DUALCO_CITYSPY.WAV": 1.3, "DUALCO_ROYAL.WAV": 1.4, "DUALCO_MMISSILE.WAV": 1.3, "DUALFR_PYROCLASM.WAV": 1.4, "DUALFR_SMOKESCREEN.WAV": 1.4, "DUALFI_WALLFLAMES.WAV": 1.6, "DUALWT_SERPENT.WAV": 1.3, "DUALWT_RITESEAS.WAV": 2.4, "DUALWT_FLASHFLOOD.WAV": 1.35, "DUALWT_CRASHWAVE.WAV": 1.3, "DUALER_TECTONIC.WAV": 1.6, "DUALDF_BLOODBATH.WAV": 2.6, "DUALDF_HFLOOP.WAV": 1.6, "DUALDF_REPENT.WAV": 1.6, "DUALDF_REPHIT.WAV": 2.9, "DUALDF_SANCTIFY.WAV": 2.6, "DUALDF_HARVEST.WAV": 1.6, "DUALDF_HARVPOP.WAV": 1.4,
         "DUALDF_HFHIT1.WAV": 2.0, "DUALDF_HFHIT2.WAV": 2.0, "DUALDF_HFHIT3.WAV": 2.0,
         "DUALDF_MARTYR.WAV": 1.5, "DUALDF_CLEANSE.WAV": 1.6, "DUALDF_PHOENIX.WAV": 1.5, "DUALDF_STARLOOP.WAV": 1.6,
         "DUALDF_STARHIT1.WAV": 1.8, "DUALDF_STARHIT2.WAV": 1.8, "DUALDF_ASHES.WAV": 1.5, "DUALDF_ASHHIT.WAV": 1.7, "DUALDF_ASHIMPACT.WAV": 1.4, "DUALEF_OILSPRING.WAV": 1.5, "DUALEF_LIONHEART.WAV": 3.0, "DUALFA_SANDSTORM.WAV": 1.4, "DUALFA_SANDHIT.WAV": 1.5, "DUALFA_IMPLOSION.WAV": 2.5, "DUALWD_SOULSIPHON.WAV": 1.8, "DUALLW_HOLYWATER.WAV": 2.2, "DUALEW_SWAMPWALK.WAV": 2.0, "DUALEA_BOULDER.WAV": 2.2, "DUALEA_GRAVITY.WAV": 1.5, "DUALEL_AWAKEN.WAV": 1.7, "DUALED_THREADS.WAV": 1.7, "DUALED_THREADHIT.WAV": 1.7, "DUALFW_BLOODBOIL.WAV": 1.5,  "DUALFA_IMPLOHIT.WAV": 1.6, "DUALFA_FRENZY.WAV": 1.8, "DUALFA_DROUGHT.WAV": 1.2, "DUALFA_DROUGHTP.WAV": 1.3, "DUALEF_FORGEBLAST.WAV": 1.8, "DUALEF_ARMSRACE.WAV": 1.5, "DUALWA_MISTYSTEP.WAV": 2.4, "DUALWA_FFRING.WAV": 2.3, "DUALWA_FLASHFREEZE.WAV": 1.8, "DUALAD_SUFFOCATE.WAV": 2.0, "DUALAD_SUFFHIT.WAV": 1.8, "DUALAD_BORROWTIME.WAV": 1.6, "DUALAD_BANSHEE.WAV": 2.4, "DUALAD_BANSHEEHIT.WAV": 1.4, "DUALLA_CHORUS.WAV": 1.95, "DUALLA_INSPIRE.WAV": 1.6, "DUALLA_SECONDWIND.WAV": 1.6, "DUALLA_ANGELWINGS.WAV": 2.4, "DUALDE_UNDYING.WAV": 1.5, "DUALDE_CALLDEAD.WAV": 2.1, "DUALAI_GUST.WAV": 1.8, "DUALER_STEADFAST.WAV": 2.4, "DUALER_STEADHIT.WAV": 1.0, "DUALAI_CROSSWIND.WAV": 1.6, "DUALAI_SUSPEND.WAV": 1.6, "DUALAI_STATICSHIELD.WAV": 2.0, "DUALDE_WITHER.WAV": 1.6, "DUALLI_MIRACLE.WAV": 1.8}


TAIL = {"DUALDF_SANCTIFY.WAV": ("choir:130.8:2.0", 0.9, 0.04)}   # 2026-10-16: (synth, seconds, level) quiet tail APPENDED after the mix ends


def add_tail(s, spec, secs, lvl):
    """Append a quiet tail AFTER the finished mix (nothing before its end changes): the middle of a synth voice that
    matches the sound (Sanctify: its own low choir note) at `lvl` of full scale, swelling in under the last 0.3 s of the
    mix's own fade (so the joint is seamless; everything earlier is untouched), dying away on a (1-x)^1.6 curve over `secs`."""
    ov = int(0.3 * RATE); v = synth(spec); mid = len(v) // 4; T = int(secs * RATE); v = v[mid:mid + ov + T]
    pk = max(1e-9, max(abs(x) for x in v)); out = list(s) + [0.0] * T; N = len(s)
    for i in range(len(v)):                                      # swells in under the last 0.3 s of the mix's own fade,
        g = (i / ov) ** 1.5 if i < ov else (1 - (i - ov) / T) ** 1.6   # then dies away after the original end
        out[N - ov + i] += v[i] / pk * lvl * g
    return out


def synth(spec):
    """'whistle:f0:f1:seconds' -> falling whistle: exponential glide f0 -> f1 with 6 Hz vibrato, a softer 2nd
    harmonic, a breathy noise band, 60 ms attack and a tail that thins out (fireworks whistle).
    'drone:f0:seconds' -> creepy enchantment sting: a tritone-stacked, slowly detuning minor drone (f0, f0*1.19,
    f0*1.414, f0*2.0) with 5.5 Hz tremolo and a dark noise swell that rises then dies away."""
    parts = spec.split(":"); kind = parts[0]
    if kind == "splash":
        # 'splash:seconds' -> a HEAVY splash into water (Misty Step v3, 2026-10-15; user: should sound like heavy
        # splashing): a deep body-plunge thump (95 -> 45 Hz, 0.25 s), a broadband wash of noise through a falling
        # low-pass (4 kHz -> 600 Hz) with an instant attack and ~0.5 s decay, a second smaller slap at 0.18 s, then
        # bubbly glugs (short rising sine chirps 180..700 Hz) and droplet patter (sparse band-passed ticks) in the tail
        secs = float(parts[1]); n = int(secs * RATE); out = [0.0] * n; rnd = random.Random(77); lp = 0.0
        for i in range(n):
            t = i / RATE
            fc = 600 + 3400 * math.exp(-t / 0.18); a = 1 - math.exp(-2 * math.pi * fc / RATE)
            lp += a * ((rnd.random() * 2 - 1) - lp)
            wash = lp * (math.exp(-t / 0.42) + 0.6 * math.exp(-max(0.0, t - 0.18) / 0.22) * (t > 0.18))
            f = 45 + 50 * math.exp(-t / 0.08); thump = math.sin(2 * math.pi * f * t) * math.exp(-t / 0.12)
            out[i] = 0.9 * wash + 0.8 * thump
        for k in range(26):                                                    # glugs
            t0 = 0.12 + rnd.random() * (secs - 0.35); f0 = rnd.uniform(180, 450); d = rnd.uniform(0.04, 0.09); g = rnd.uniform(0.12, 0.3) * math.exp(-t0 / 0.8)
            i0 = int(t0 * RATE); ph = 0.0
            for j in range(int(d * RATE)):
                if i0 + j >= n: break
                u = j / (d * RATE); ph += f0 * (1 + 0.8 * u) / RATE
                out[i0 + j] += g * math.sin(2 * math.pi * ph) * math.sin(math.pi * u)
        y1 = y2 = 0.0; w = 2 * math.pi * 2600 / RATE; q = 0.9
        for k in range(40):                                                    # droplet patter
            t0 = 0.25 + rnd.random() * (secs - 0.3); i0 = int(t0 * RATE); g = rnd.uniform(0.05, 0.15)
            for j in range(int(0.012 * RATE)):
                if i0 + j >= n: break
                x = (rnd.random() * 2 - 1) * math.exp(-j / (0.003 * RATE))
                y = x + 2 * q * math.cos(w) * y1 - q * q * y2; y2 = y1; y1 = y; out[i0 + j] += g * y * 0.3
        tail = int(0.06 * RATE)
        for i in range(tail): out[n - 1 - i] *= i / tail
        return out
    if kind == "glasswind":
        # 'glasswind:f0:f1:seconds' -> Flashfreeze ring v3 (2026-10-15; user: like Implosion's winding sound but icy):
        # Implosion's winding wind-up re-voiced as GLASS - inharmonic bowl partials (1, 2.32, 4.25, 6.63 x f) with a
        # slow chorus (+-0.6 %% twins) gliding f0 -> f1 on an eased curve, a 6 -> 14 Hz shimmer tremolo speeding up as it
        # winds, brighter upper partials as it swells (u^1.3), and a 20 ms cut
        f0, f1, secs = float(parts[1]), float(parts[2]), float(parts[3]); n = int(secs * RATE); out = []
        parts_ = ((1.0, 1.0), (2.32, 0.55), (4.25, 0.32), (6.63, 0.18)); ph = [[0.0, 0.0, 0.0] for _ in parts_]; tph = 0.0
        for i in range(n):
            u = i / n; e = u * u * (3 - 2 * u); f = f0 * (f1 / f0) ** e
            tph += (6 + 8 * u) / RATE; trem = 0.7 + 0.3 * math.sin(2 * math.pi * tph)
            v = 0.0
            for k, (m, g) in enumerate(parts_):
                gg = g * (1.0 if k == 0 else (0.25 + 0.75 * u ** 1.3))
                for d, det in enumerate((1.0, 1.006, 0.994)):
                    ph[k][d] += f * m * det / RATE; v += gg * math.sin(2 * math.pi * ph[k][d]) / 3
            env = (0.1 + 0.9 * u ** 1.3) * min(1.0, (n - i) / (0.02 * RATE))
            out.append(0.4 * env * v * trem)
        return out
    if kind == "tick":
        # 'tick:ping:body:seconds' -> a mechanical CLOCK tick (Borrow Time v6, 2026-10-16): a 2 ms click of noise, a
        # metallic escapement ping (resonance at 'ping' Hz, ~30 ms) and a hollow wooden case thump (resonance at 'body'
        # Hz, ~70 ms), then a smaller second click 14 ms later (the escapement catching) - tick/tock by pitch
        fp, fb, secs = float(parts[1]), float(parts[2]), float(parts[3]); n = int(secs * RATE); out = [0.0] * n
        rnd = random.Random(int(fp))
        for (t0, g) in ((0.0, 1.0), (0.014, 0.45)):
            i0 = int(t0 * RATE); y1 = y2 = z1 = z2 = 0.0
            wp = 2 * math.pi * fp / RATE; wb = 2 * math.pi * fb / RATE
            for k in range(n - i0):
                x = (rnd.random() * 2 - 1) if k < int(0.002 * RATE) else 0.0
                y = x + 2 * 0.9985 * math.cos(wp) * y1 - 0.9985 ** 2 * y2; y2 = y1; y1 = y
                z = x + 2 * 0.9993 * math.cos(wb) * z1 - 0.9993 ** 2 * z2; z2 = z1; z1 = z
                t = k / RATE
                out[i0 + k] += g * (0.6 * x + 0.05 * y * math.exp(-t / 0.03) + 0.04 * z * math.exp(-t / 0.07))
        return out
    if kind == "gasp":
        # 'gasp:seconds:strain' -> a human GASP for air (Suffocate v4, 2026-10-16): breath noise rushing in through an open
        # throat = white noise through two vowel formants (F1 650->900 Hz, F2 1150->1700 Hz rising as the throat
        # tightens) + a thin high hiss; the level climbs to ~80 %% of the length then cuts off sharply (the throat
        # closing); 'strain' (0..1) adds a strangled voiced edge - irregular 90-140 Hz glottal pulses through the same
        # formants - in the last half
        secs, strain = float(parts[1]), float(parts[2]); n = int(secs * RATE); out = []; rnd = random.Random(int(secs * 1000) + 7)
        st = [[0.0, 0.0], [0.0, 0.0], [0.0, 0.0]]; per = 0.0; nxt = 0
        def bp(i_, x, fc, q):
            w = 2 * math.pi * fc / RATE; y = x + 2 * q * math.cos(w) * st[i_][0] - q * q * st[i_][1]; st[i_][1] = st[i_][0]; st[i_][0] = y; return y
        for i in range(n):
            u = i / n
            env = (u / 0.8) ** 1.6 if u < 0.8 else max(0.0, 1 - (u - 0.8) / 0.06)
            x = rnd.random() * 2 - 1
            if strain > 0 and u > 0.45 and i >= nxt:                         # a glottal pulse
                x += 6.0 * strain; nxt = i + int(RATE / rnd.uniform(90, 140))
            f1 = 650 + 250 * u; f2 = 1150 + 550 * u
            y = 0.035 * bp(0, x, f1, 0.985) + 0.025 * bp(1, x, f2, 0.98) + 0.012 * bp(2, rnd.random() * 2 - 1, 4200, 0.9)
            out.append(env * y)
        return out
    if kind == "icering":
        # 'icering:seconds' -> Flashfreeze's shrinking ring v2 (2026-10-15; user: try a new shrinking-circle sound):
        # a cold glassy in-rush - airy noise through a band-pass climbing 900 -> 5000 Hz, a dense hail of crystal
        # tinkles (short 2.5..7 kHz pings, 15 ms decay) whose rate climbs 8 -> 90 /s, ice-creak crackles (resonant 380 Hz
        # clicks) and a falling-then-rising glass tone; everything swells u^1.4 to a sharp 20 ms cut
        secs = float(parts[1]); n = int(secs * RATE); out = [0.0] * n; rnd = random.Random(83); y1 = y2 = 0.0; ph = 0.0
        for i in range(n):
            t = i / RATE; u = i / n
            fc = 900 * (5000 / 900) ** (u ** 1.2); w = 2 * math.pi * fc / RATE; q = 0.96
            x = rnd.random() * 2 - 1; y = x + 2 * q * math.cos(w) * y1 - q * q * y2; y2 = y1; y1 = y
            f = 1800 * (2 ** (1.4 * u * u - 0.3 * u)); ph += f / RATE
            out[i] = (0.05 * y + 0.12 * math.sin(2 * math.pi * ph) * (0.6 + 0.4 * math.sin(2 * math.pi * 11 * t))) * (0.15 + 0.85 * u ** 1.4)
        t = 0.0
        while t < secs:
            u = t / secs; t += rnd.expovariate(8 + 82 * u ** 1.5)
            i0 = int(t * RATE); f = rnd.uniform(2500, 7000); g = rnd.uniform(0.08, 0.22) * (0.3 + 0.7 * u)
            for j in range(int(0.04 * RATE)):
                if i0 + j >= n: break
                out[i0 + j] += g * math.sin(2 * math.pi * f * j / RATE) * math.exp(-j / (0.015 * RATE))
        for k in range(14):
            t0 = rnd.random() * secs; i0 = int(t0 * RATE); g = 0.25 * (0.3 + 0.7 * t0 / secs)
            for j in range(int(0.03 * RATE)):
                if i0 + j >= n: break
                out[i0 + j] += g * math.sin(2 * math.pi * 380 * j / RATE) * math.exp(-j / (0.006 * RATE)) * (1 if rnd.random() < 0.7 else -1) * 0.6
        cut = int(0.02 * RATE)
        for i in range(cut): out[n - 1 - i] *= i / cut
        return out
    if kind == "hiss":
        # 'hiss:seconds' -> a SOFT steam hiss (Steam Power v3, 2026-10-14; user: still explosive): white noise through
        # a gentle high band-pass (~3.5 kHz, low Q), a slow 0.18 s swell and a long smooth fade - no transient at all
        secs = float(parts[1]); n = int(secs * RATE); out = []; rnd = random.Random(61); y1 = y2 = 0.0
        w = 2 * math.pi * 3500 / RATE; q = 0.86
        for i in range(n):
            x = rnd.random() * 2 - 1
            y = x + 2 * q * math.cos(w) * y1 - q * q * y2; y2 = y1; y1 = y
            u = i / n; env = min(1.0, i / (0.18 * RATE)) * (1 - u) ** 1.4
            out.append(0.25 * env * y)
        return out
    if kind == "subswell":
        # 'subswell:f0:f1:seconds' -> a deep sub-bass swell (Implosion v11): a sine + soft 2nd harmonic gliding f0 -> f1,
        # level rising u^1.5 to full, 20 ms cut - the 'full' low end under the horns
        f0, f1, secs = float(parts[1]), float(parts[2]), float(parts[3]); n = int(secs * RATE); out = []; ph = 0.0
        for i in range(n):
            u = i / n; ph += (f0 + (f1 - f0) * u) / RATE
            env = (0.15 + 0.85 * u ** 1.5) * min(1.0, i / (0.05 * RATE)) * min(1.0, (n - i) / (0.02 * RATE))
            out.append(0.8 * env * (math.sin(2 * math.pi * ph) + 0.3 * math.sin(4 * math.pi * ph)))
        return out
    if kind == "growlhorn":
        # 'growlhorn:f0:f1:seconds' -> Implosion v10 (2026-10-14; user: the winding horn is the right idea but wacky -
        # grittier, magical): a gentle eased wind-up f0 -> f1, almost no vibrato, brass harmonics 1..12 brightening with
        # level, a 0.6 % detuned second voice (chorus) and a sub-octave for weight, and GRIT = amplitude roughened by
        # low-passed random noise (a 25-60 Hz growl); 80 ms attack, swelling level, 20 ms cut
        f0, f1, secs = float(parts[1]), float(parts[2]), float(parts[3]); n = int(secs * RATE); out = []
        ph = ph2 = ph3 = 0.0; rnd = random.Random(53); g = 0.0; gt = 0.0
        for i in range(n):
            u = i / n; e = u * u * (3 - 2 * u)
            f = f0 * (f1 / f0) ** e * (1 + 0.002 * math.sin(2 * math.pi * 4.5 * i / RATE))
            ph += f / RATE; ph2 += f * 1.006 / RATE; ph3 += f * 0.5 / RATE
            lvl = 0.35 + 0.65 * u ** 1.2; roll = 1.5 - 0.8 * lvl
            tone = sum((math.sin(2 * math.pi * k * ph) + 0.7 * math.sin(2 * math.pi * k * ph2)) / k ** roll for k in range(1, 13))
            sub = 0.5 * math.sin(2 * math.pi * ph3)
            gt += (25 + 35 * u) / RATE
            if gt >= 1.0: gt -= 1.0; g = rnd.uniform(-1, 1)
            grit = 1 + (0.35 + 0.25 * u) * g
            env = lvl * min(1.0, i / (0.08 * RATE)) * min(1.0, (n - i) / (0.02 * RATE))
            out.append(0.2 * env * (tone + sub) * grit)
        return out
    if kind == "horn":
        # 'horn:f0:f1:seconds' -> a WINDING horn (Implosion v9, 2026-10-14): a brassy tone (harmonics 1..12, rolloff
        # that opens up as it swells = brighter when louder, like real brass) whose pitch winds up f0 -> f1 (eased
        # exponential, like a siren spinning up), 5 Hz vibrato deepening, 80 ms attack, swelling level, 20 ms cut
        f0, f1, secs = float(parts[1]), float(parts[2]), float(parts[3]); n = int(secs * RATE); out = []
        ph = 0.0
        for i in range(n):
            u = i / n; e = u * u * (3 - 2 * u)
            f = f0 * (f1 / f0) ** e * (1 + (0.004 + 0.012 * u) * math.sin(2 * math.pi * 5.0 * i / RATE))
            ph += f / RATE
            lvl = 0.35 + 0.65 * u ** 1.2; roll = 1.6 - 0.9 * lvl
            tone = sum(math.sin(2 * math.pi * k * ph) / k ** roll for k in range(1, 13))
            env = lvl * min(1.0, i / (0.08 * RATE)) * min(1.0, (n - i) / (0.02 * RATE))
            out.append(0.32 * env * tone)
        return out
    if kind == "laser":
        # 'laser:f0:f1:seconds' -> a sci-fi laser charge-up (Implosion v7, 2026-10-14): a buzzy saw-like tone (harmonics
        # 1..6 at 1/k) plus a 0.8 %% detuned twin (phasing) sweeping f0 -> f1 exponentially, a pulsing tremolo that
        # speeds up 9 -> 34 Hz as it charges, level rising to full, a bright zap partial in the last 15 %%, 15 ms cut
        f0, f1, secs = float(parts[1]), float(parts[2]), float(parts[3]); n = int(secs * RATE); out = []
        ph = ph2 = tp = 0.0
        for i in range(n):
            u = i / n; f = f0 * (f1 / f0) ** (u ** 1.25)
            ph += f / RATE; ph2 += f * 1.008 / RATE; tp += (9 + 25 * u * u) / RATE
            saw = sum(math.sin(2 * math.pi * k * ph) / k for k in range(1, 7)) + 0.8 * sum(math.sin(2 * math.pi * k * ph2) / k for k in range(1, 5))
            trem = 0.62 + 0.38 * math.sin(2 * math.pi * tp)
            zap = math.sin(2 * math.pi * 3.0 * ph) * max(0.0, (u - 0.85) / 0.15) * 0.8
            env = (0.25 + 0.75 * u ** 1.3) * min(1.0, (n - i) / (0.015 * RATE)) * min(1.0, i / (0.02 * RATE))
            out.append(env * (0.3 * saw * trem + 0.3 * zap))
        return out
    if kind == "vacuum":
        # 'vacuum:seconds' -> a magical vacuum (Implosion's ring, 2026-10-14): white noise through a 2-pole band-pass
        # whose centre climbs 250 -> 2600 Hz (air being sucked inward), level swelling (u^1.6) to the end, plus a thin
        # rising sine shimmer (180 -> 1400 Hz, 7 Hz tremolo, a 1.5x partial) and a low suction hum; a 25 ms cut at the end
        secs = float(parts[1]); n = int(secs * RATE); out = []; rnd = random.Random(41)
        y1 = y2 = 0.0; ph = ph2 = 0.0
        for i in range(n):
            t = i / RATE; u = i / n
            fc = 250 * (2600 / 250) ** (u ** 1.3); q = 0.975 - 0.02 * u
            w = 2 * math.pi * fc / RATE
            x = rnd.random() * 2 - 1
            y = x + 2 * q * math.cos(w) * y1 - q * q * y2; y2 = y1; y1 = y
            f = 180 * (1400 / 180) ** (u ** 1.5); ph += f / RATE; ph2 += 1.5 * f / RATE
            trem = 0.75 + 0.25 * math.sin(2 * math.pi * 7 * t)
            shim = (math.sin(2 * math.pi * ph) + 0.4 * math.sin(2 * math.pi * ph2)) * trem
            hum = math.sin(2 * math.pi * (55 + 40 * u) * t)
            env = (0.08 + 0.92 * u ** 1.6) * min(1.0, (n - i) / (0.025 * RATE))
            out.append(env * (0.06 * y + 0.35 * shim + 0.25 * hum * (1 - 0.5 * u)))
        return out
    if kind == "choir":
        # 'choir:f0:seconds[:minor]' -> a sung CHORD (Life/Air v5, 2026-10-16): root + third + fifth + octave, each note 4
        # slightly detuned voices (a band-limited glottal saw, harmonics 1..24 at 1/k^1.2) with their own 4.8-5.6 Hz
        # vibrato, through the 'ah' vowel formants (F1 730, F2 1090, F3 2440, F4 3400); a 0.5 s swell, a 0.8 s release
        f0, secs = float(parts[1]), float(parts[2]); minor = len(parts) > 3 and parts[3] == "minor"
        n = int(secs * RATE); out = []; rnd = random.Random(int(f0 * 10) + (7 if minor else 0))
        notes = (1.0, 1.189 if minor else 1.26, 1.498, 2.0)
        voices = [[f0 * m * (1 + rnd.uniform(-0.007, 0.007)), rnd.uniform(4.8, 5.6), rnd.uniform(0, 6.28), 0.0] for m in notes for _ in range(4)]
        F = ((730, 0.992, 1.0), (1090, 0.99, 0.55), (2440, 0.985, 0.3), (3400, 0.98, 0.15)); st = [[0.0, 0.0] for _ in F]
        for i in range(n):
            t = i / RATE; x = 0.0
            for vo in voices:
                f = vo[0] * (1 + 0.006 * math.sin(2 * math.pi * vo[1] * t + vo[2])); vo[3] += f / RATE
                ph = vo[3]; x += sum(math.sin(2 * math.pi * k * ph) / k ** 1.2 for k in range(1, 25) if f * k < 7000)
            y = 0.0
            for k, (fc, q, g) in enumerate(F):
                w = 2 * math.pi * fc / RATE; v = x + 2 * q * math.cos(w) * st[k][0] - q * q * st[k][1]; st[k][1] = st[k][0]; st[k][0] = v; y += g * v
            env = min(1.0, t / 0.5) * (1.0 if t < secs - 0.8 else max(0.0, (secs - t) / 0.8))
            out.append(0.0009 * env * y)
        return out
    if kind == "drum":
        # 'drum:f0:seconds' -> a TIMPANI-like hit: a sine dropping from 1.6x to f0 in 40 ms, a 2.76x partial, a felt-mallet
        # noise click, ~0.6 s decay
        f0, secs = float(parts[1]), float(parts[2]); n = int(secs * RATE); out = []; rnd = random.Random(int(f0)); ph = ph2 = 0.0
        for i in range(n):
            t = i / RATE; f = f0 * (1 + 0.6 * math.exp(-t / 0.04)); ph += f / RATE; ph2 += 2.76 * f / RATE
            v = math.sin(2 * math.pi * ph) * math.exp(-t / 0.55) + 0.3 * math.sin(2 * math.pi * ph2) * math.exp(-t / 0.18)
            v += (rnd.random() * 2 - 1) * math.exp(-t / 0.008) * 0.6
            out.append(0.8 * v)
        return out
    if kind == "strings":
        # 'strings:f0:seconds' -> an ORCHESTRAL STRING chord (Inspiration v4, 2026-10-16): a major triad + octave (f0, 1.26,
        # 1.5, 2.0 x f0), each note a little ensemble of 3 detuned band-limited saws (harmonics 1..10 at 1/k) with its own
        # slow 5.2-5.8 Hz vibrato, through a gentle low-pass that opens as the bow digs in; a slow 0.45 s swell, a
        # sustain and a 0.6 s release
        f0, secs = float(parts[1]), float(parts[2]); n = int(secs * RATE); out = []; rnd = random.Random(int(f0))
        voices = []
        for m in (1.0, 1.26, 1.5, 2.0):
            for det in (-0.006, 0.0, 0.007):
                voices.append([f0 * m * (1 + det), rnd.uniform(5.2, 5.8), rnd.uniform(0, 6.28), 0.0, 0.7 if m < 1.9 else 0.45])
        lp = 0.0
        for i in range(n):
            t = i / RATE; u = i / n
            v = 0.0
            for vo in voices:
                f = vo[0] * (1 + 0.004 * math.sin(2 * math.pi * vo[1] * t + vo[2])); vo[3] += f / RATE; ph = vo[3]
                sw = sum(math.sin(2 * math.pi * k * ph) / k for k in range(1, 11))
                v += vo[4] * sw
            env = min(1.0, t / 0.45) * (1.0 if t < secs - 0.6 else max(0.0, (secs - t) / 0.6))
            a = 0.08 + 0.12 * min(1.0, t / 0.6)                                    # the low-pass opening
            lp += a * (v - lp)
            out.append(0.012 * env * lp)
        return out
    if kind == "glide":
        # 'glide:<Sfx-relative path>:s0:s1:seconds' -> a SAMPLE played with a smoothly gliding pitch/speed s0 -> s1 (linear
        # interpolation read; Suffocate v10, 2026-10-16: Vaporize's sound starting deep and rising)
        rel, s0, s1, secs = parts[1], float(parts[2]), float(parts[3]), float(parts[4])
        cpow = float(parts[5]) if len(parts) > 5 else 1.0                       # optional curve: < 1 = rises fast early (ease-out)
        rate, src = load_mono(os.path.join(SFX, rel)); n = int(secs * RATE); out = []; pos = 0.0; L = len(src)
        for i in range(n):
            u = i / n; k = int(pos)
            if k + 1 >= L: break
            fr = pos - k; out.append(src[k] * (1 - fr) + src[k + 1] * fr)
            pos += (s0 + (s1 - s0) * u ** cpow) * rate / RATE
        return out
    if kind == "croak":
        # 'croak:rate:seconds' -> a GRUDGE-style croak (Suffocate v8, 2026-10-16: "uhhh... uh... uh... uhhhh... uh"):
        # vocal fry = slow, irregular glottal pulses (~rate Hz, +-18 %% jitter, the rate sagging ~25 %% over the croak)
        # each ringing three 'uh' formants (F1 620, F2 1180, F3 2500 Hz), a breathy noise edge; quick swell, sustain,
        # then a sagging fade - the long ones read as 'uhhhh', the short ones as 'uh'
        rate, secs = float(parts[1]), float(parts[2]); n = int(secs * RATE); out = []; rnd = random.Random(int(rate * 100 + secs * 1000))
        F = ((620, 0.9965, 1.0), (1180, 0.996, 0.6), (2500, 0.993, 0.25)); st = [[0.0, 0.0] for _ in F]; nxt = 0; lvl = 1.0
        for i in range(n):
            u = i / n; x = 0.0
            if i >= nxt:
                x = lvl; lvl = rnd.uniform(0.6, 1.0)
                nxt = i + int(RATE / (rate * (1 - 0.25 * u) * rnd.uniform(0.82, 1.18)))
            x += (rnd.random() * 2 - 1) * 0.04                                  # breath
            y = 0.0
            for k, (fc, q, g) in enumerate(F):
                w = 2 * math.pi * fc / RATE; v = x + 2 * q * math.cos(w) * st[k][0] - q * q * st[k][1]; st[k][1] = st[k][0]; st[k][0] = v; y += g * v
            env = min(1.0, u / 0.08) * (1.0 if u < 0.6 else (1 - (u - 0.6) / 0.4) ** 1.2)
            out.append(0.012 * env * y)
        return out
    if kind == "rattle":
        # 'rattle:rate0:rate1:seconds' -> a throaty k-k-k-k death rattle (the Grudge): a train of short clicks whose
        # rate glides rate0 -> rate1 Hz; each click = a 120 Hz thump + a burst of noise through a ~900 Hz resonance,
        # 22 ms decay, slight random timing/level jitter; whole thing swells in and dies away
        r0, r1, secs = float(parts[1]), float(parts[2]), float(parts[3])
        n = int(secs * RATE); out = []; rnd = random.Random(23); phase = 0.0; burst_t = 1.0; lvl = 1.0
        y1 = y2 = 0.0; w = 2 * math.pi * 900 / RATE; q = 0.93
        for i in range(n):
            t = i / RATE; u = i / n
            rate = r0 + (r1 - r0) * u
            phase += rate / RATE
            if phase >= 1.0:
                phase -= 1.0 + rnd.uniform(-0.12, 0.12); burst_t = 0.0; lvl = rnd.uniform(0.7, 1.0)
            burst_t += 1.0 / RATE
            benv = math.exp(-burst_t / 0.022) * lvl
            x = (rnd.random() * 2 - 1) * benv
            y = x + 2 * q * math.cos(w) * y1 - q * q * y2; y2 = y1; y1 = y                 # resonant 2-pole
            thump = math.sin(2 * math.pi * 120 * burst_t) * math.exp(-burst_t / 0.012) * lvl
            env = min(1.0, u / 0.12) * (1 - u) ** 0.8
            out.append(env * (0.22 * y + 0.9 * thump))
        return out
    if kind == "wind":
        # 'wind:seconds' -> gusting wind: white noise through a wandering 2-pole band-pass (centre drifting 350..900 Hz)
        # with a slow gust LFO (two detuned sub-Hz sines) on the level, a faint 60 Hz rumble under the gusts, 0.25 s
        # swell in, dying away over the last 30 %
        secs = float(parts[1]); n = int(secs * RATE); out = []; rnd = random.Random(31)
        y1 = y2 = 0.0; q = 0.985
        for i in range(n):
            t = i / RATE; u = i / n
            fc = 600 + 250 * math.sin(2 * math.pi * 0.23 * t) + 120 * math.sin(2 * math.pi * 0.61 * t + 1.0)
            w = 2 * math.pi * fc / RATE
            x = rnd.random() * 2 - 1
            y = x + 2 * q * math.cos(w) * y1 - q * q * y2; y2 = y1; y1 = y
            gust = 0.55 + 0.45 * (0.5 * math.sin(2 * math.pi * 0.42 * t) + 0.5 * math.sin(2 * math.pi * 0.77 * t + 2.0))
            rumble = 0.25 * gust * gust * math.sin(2 * math.pi * 60 * t)
            env = min(1.0, t / 0.25) * (1.0 if u < 0.7 else (1 - u) / 0.3)
            out.append(env * (0.09 * y * gust + rumble))
        return out
    if kind == "shimmer":
        # 'shimmer:seconds' -> a magical airy shimmer: six detuned high sines (1.1..2.6 kHz) with slow independent vibrato,
        # each fading in and out on its own 0.4..0.9 Hz cycle, through a soft swell; sits on top of the wind bed
        secs = float(parts[1]); n = int(secs * RATE); out = []; rnd = random.Random(37)
        voices = [(rnd.uniform(1100, 2600), rnd.uniform(0.4, 0.9), rnd.uniform(0, 6.28), rnd.uniform(3, 6)) for _ in range(6)]
        ph = [0.0] * 6
        for i in range(n):
            t = i / RATE; u = i / n; v = 0.0
            for k2, (f, lfo, p0, vib) in enumerate(voices):
                ph[k2] += 2 * math.pi * f * (1 + 0.004 * math.sin(2 * math.pi * vib * t)) / RATE
                v += (0.5 + 0.5 * math.sin(2 * math.pi * lfo * t + p0)) * math.sin(ph[k2])
            env = min(1.0, t / 0.3) * (1.0 if u < 0.75 else (1 - u) / 0.25)
            out.append(env * 0.07 * v)
        return out
    if kind == "bronzering":
        # 'bronzering:f0:seconds' -> Steadfast v2 (2026-10-17, user: try something new): a struck bronze SHIELD - the
        # inharmonic modes of a clamped circular plate (1, 1.59, 2.14, 2.65, 3.16, 3.65 x f0) with slow beating pairs
        # (each mode doubled 0.6..1.8 Hz apart), a 3 ms knock of filtered noise, and a long low HUM: the fundamental
        # decays slowest and swells back once (the plate's breathing), higher modes die fast
        f0, secs = float(parts[1]), float(parts[2]); n = int(secs * RATE); out = []; rnd = random.Random(218)
        ratios = (1.0, 1.59, 2.14, 2.65, 3.16, 3.65); gains = (1.0, 0.55, 0.42, 0.28, 0.18, 0.12)
        decays = (0.9, 2.2, 3.4, 4.8, 6.5, 8.0); beats = (0.6, 0.9, 1.3, 1.5, 1.8, 1.1)
        ph = [0.0] * 12; y1 = 0.0
        for i in range(n):
            t = i / RATE; u = i / n; v = 0.0
            for k in range(6):
                for s2 in (0, 1):
                    ph[2 * k + s2] += 2 * math.pi * f0 * ratios[k] * (1 + (0.5 if s2 else -0.5) * beats[k] / (f0 * ratios[k])) / RATE
                    v += 0.5 * gains[k] * math.exp(-decays[k] * t) * math.sin(ph[2 * k + s2])
            hum = 0.25 * math.sin(math.pi * min(1.0, t / (0.7 * secs))) * math.sin(ph[0] * 0.5)
            x = rnd.random() * 2 - 1; y1 = 0.6 * y1 + 0.4 * x
            knock = y1 * math.exp(-t / 0.003) * 0.6
            out.append((0.42 * v + hum * (1 - u) + knock) * min(1.0, t / 0.002) * (1 - u) ** 0.5)
        return out
    if kind == "crackle":
        # 'crackle:density:seconds' (Smokescreen 2026-10-17) -> embers popping inside smoke: sparse random clicks
        # (Poisson, `density` per second, slowly thinning) - each a 1.5-4 ms burst of noise through a ~2.4 kHz
        # resonance with a tiny 300 Hz knock, random level; swells in over 0.15 s and dies away over the last 40 %
        dens, secs = float(parts[1]), float(parts[2]); n = int(secs * RATE); out = []; rnd = random.Random(2251)
        y1 = y2 = 0.0; w = 2 * math.pi * 2400 / RATE; q = 0.9; bt = 1.0; lvl = 0.0; dec = 0.003
        for i in range(n):
            t = i / RATE; u = i / n
            if rnd.random() < dens * (1.0 - 0.5 * u) / RATE:
                bt = 0.0; lvl = rnd.uniform(0.35, 1.0); dec = rnd.uniform(0.0015, 0.004)
            bt += 1.0 / RATE
            benv = math.exp(-bt / dec) * lvl
            x = (rnd.random() * 2 - 1) * benv
            y = x + 2 * q * math.cos(w) * y1 - q * q * y2; y2 = y1; y1 = y
            knock = math.sin(2 * math.pi * 300 * bt) * math.exp(-bt / 0.004) * lvl * 0.5
            env = min(1.0, t / 0.15) * (1.0 if u < 0.6 else (1 - u) / 0.4)
            out.append(env * (0.3 * y + knock))
        return out
    if kind == "zip":
        # 'zip:f0:f1:seconds:sweep' -> Magic Missile v7 (2026-10-18, user: scrap it, something NEW): a bright arcane 'pew' -
        # a sine + soft triangle (odd harmonics 3,5 at 1/9,1/25) diving exponentially f0 -> f1 within 'sweep' seconds
        # then holding, a 2 ms attack and a fast exponential decay (tau 0.09 s), 7 Hz vibrato creeping in on the tail
        f0, f1, secs, sw = float(parts[1]), float(parts[2]), float(parts[3]), float(parts[4]); n = int(secs * RATE); out = []; ph = 0.0
        for i in range(n):
            t = i / RATE; e = min(1.0, t / sw); f = f0 * (f1 / f0) ** (1 - (1 - e) ** 2)
            f *= 1 + 0.012 * min(1.0, t / 0.2) * math.sin(2 * math.pi * 7 * t)
            ph += f / RATE; p = 2 * math.pi * ph
            v = math.sin(p) + math.sin(3 * p) / 9 + math.sin(5 * p) / 25
            env = min(1.0, t / 0.002) * math.exp(-t / 0.09) * min(1.0, (n - i) / (0.01 * RATE))
            out.append(0.5 * env * v)
        return out
    if kind == "airwhoosh":
        # 'airwhoosh:fc0:fc1:seconds' -> a soft airy whoosh: white noise through a resonant 2-pole band-pass whose centre
        # glides fc0 -> fc1 (exponential), on a smooth sin^2 bump envelope (no click), slightly breathy (q 0.97)
        fa, fb, secs = float(parts[1]), float(parts[2]), float(parts[3]); n = int(secs * RATE); out = []; rnd = random.Random(int(fa))
        y1 = y2 = 0.0; q = 0.97
        for i in range(n):
            u = i / n; fc = fa * (fb / fa) ** u; w = 2 * math.pi * fc / RATE
            x = rnd.random() * 2 - 1
            y = (1 - q) * x + 2 * q * math.cos(w) * y1 - q * q * y2; y2 = y1; y1 = y
            out.append(0.9 * y * math.sin(math.pi * min(1.0, u ** 0.6)) ** 2)
        return out
    if kind == "tine":
        # 'tine:f0:seconds' -> a struck magical TINE (kalimba / glass harp): fundamental + the tine's inharmonic modes
        # (5.4x, 8.9x) that die fast, a 1 ms pluck click, gentle 0.4 %% shimmer between twin fundamentals, decay tau 0.35 s
        f0, secs = float(parts[1]), float(parts[2]); n = int(secs * RATE); out = []; ph = [0.0] * 4; rnd = random.Random(int(f0))
        modes = ((1.0, 1.0, 0.35), (1.004, 0.6, 0.35), (5.4, 0.35, 0.05), (8.9, 0.18, 0.025))
        for i in range(n):
            t = i / RATE; v = 0.0
            for k, (m, g, tau) in enumerate(modes):
                ph[k] += 2 * math.pi * f0 * m / RATE; v += g * math.exp(-t / tau) * math.sin(ph[k])
            click = (rnd.random() * 2 - 1) * math.exp(-t / 0.0008) * 0.3
            out.append((0.4 * v + click) * min(1.0, t / 0.001) * min(1.0, (n - i) / (0.02 * RATE)))
        return out
    if kind == "harp":
        # 'harp:f0:seconds' -> Lucky v2 (2026-10-18): a warm plucked HARP string (Karplus-Strong): a noise burst in a
        # delay line one period long, averaged (low-passed) each pass so the tone mellows as it rings; a soft 3 ms
        # attack, decay ~ seconds; gentle (no glassy click) - the luck arpeggio's voice
        f0, secs = float(parts[1]), float(parts[2]); n = int(secs * RATE); rnd = random.Random(int(f0 * 7))
        P = max(2, int(round(RATE / f0))); buf = [rnd.random() * 2 - 1 for _ in range(P)]
        # pre-soften the excitation (a pluck with a finger, not a pick)
        for _ in range(2):
            buf = [0.5 * (buf[k] + buf[k - 1]) for k in range(P)]
        out = []; idx = 0; damp = 0.996
        for i in range(n):
            a = buf[idx]; b = buf[(idx + 1) % P]
            buf[idx] = damp * 0.5 * (a + b); idx = (idx + 1) % P
            t = i / RATE
            out.append(a * min(1.0, t / 0.003) * min(1.0, (n - i) / (0.05 * RATE)))
        return out
    if kind == "seekcharge":
        # 'seekcharge:f0:f1:seconds' -> Seeker Bolts charge-up (2026-10-18; user: POWERFUL, no crystal pings, no
        # distortion): three slightly detuned saw-like voices (harmonics 1..10, rolloff opening 2.2 -> 1.2 as it charges)
        # rising f0 -> f1 on an eased exponential, a sub-octave sine for weight, an amplitude PULSE that speeds up 5 ->
        # 20 Hz (the three orbs spinning faster), a band-passed noise 'suck' climbing 300 -> 2400 Hz, level rising to
        # full; 40 ms attack, 25 ms cut at the end (the launch cue takes over)
        f0, f1, secs = float(parts[1]), float(parts[2]), float(parts[3]); n = int(secs * RATE); out = []
        rnd = random.Random(3751); ph = [0.0, 0.0, 0.0]; phs = 0.0; pp = 0.0; y1 = y2 = 0.0
        for i in range(n):
            u = i / n; e = u ** 1.4; f = f0 * (f1 / f0) ** e
            roll = 2.2 - 1.0 * u; tone = 0.0
            for v, det in enumerate((1.0, 1.007, 0.994)):
                ph[v] += f * det / RATE
                tone += sum(math.sin(2 * math.pi * k * ph[v]) / k ** roll for k in range(1, 11))
            phs += 0.5 * f / RATE; sub = math.sin(2 * math.pi * phs)
            pp += (5 + 15 * u ** 1.3) / RATE; pulse = 0.68 + 0.32 * math.sin(2 * math.pi * pp)
            fc = 300 * (2400 / 300) ** u; w = 2 * math.pi * fc / RATE; q = 0.94
            x = rnd.random() * 2 - 1; y = x + 2 * q * math.cos(w) * y1 - q * q * y2; y2 = y1; y1 = y
            env = (0.2 + 0.8 * u ** 1.2) * min(1.0, i / (0.04 * RATE)) * min(1.0, (n - i) / (0.025 * RATE))
            out.append(env * (0.2 * tone * pulse + 0.22 * sub * (0.4 + 0.6 * u) + 0.035 * y * u * u))
        return out
    if kind == "seeklaunch":
        # 'seeklaunch:seconds' -> Seeker Bolts launch (played by patch_tc_seekerbolts_v1.py at the release tick): a
        # punchy body thump (sine 150 -> 45 Hz in 90 ms, 3 ms attack, tau 0.12 s), a short detuned brass-ish blast at
        # 110/165 Hz (tau 0.09 s), and a whoosh-zap = noise through a resonant band-pass sweeping 3200 -> 450 Hz
        # (tau 0.22 s) under a pitch-diving 900 -> 160 Hz saw 'zap' (60 ms) - nothing ringing, nothing clipped
        secs = float(parts[1]); n = int(secs * RATE); out = []; rnd = random.Random(3752)
        ph = ph1 = ph2 = phz = 0.0; y1 = y2 = 0.0
        for i in range(n):
            t = i / RATE; att = min(1.0, t / 0.003)
            ph += (45 + 105 * math.exp(-t / 0.035)) / RATE; thump = math.sin(2 * math.pi * ph) * math.exp(-t / 0.12)
            ph1 += 110 / RATE; ph2 += 165.6 / RATE
            blast = sum((math.sin(2 * math.pi * k * ph1) + 0.8 * math.sin(2 * math.pi * k * ph2)) / k ** 1.5 for k in range(1, 8)) * math.exp(-t / 0.09)
            fc = 450 + 2750 * math.exp(-t / 0.09); w = 2 * math.pi * fc / RATE; q = 0.93
            x = rnd.random() * 2 - 1; y = x + 2 * q * math.cos(w) * y1 - q * q * y2; y2 = y1; y1 = y
            whoosh = y * math.exp(-t / 0.22) * min(1.0, t / 0.008)
            phz += (160 + 740 * math.exp(-t / 0.02)) / RATE
            zap = sum(math.sin(2 * math.pi * k * phz) / k for k in range(1, 6)) * math.exp(-t / 0.06)
            out.append(att * (0.7 * thump + 0.22 * blast + 0.06 * whoosh + 0.14 * zap))
        return out
    if kind == "seekhit":
        # 'seekhit:seconds' -> Seeker Bolts impact: a deep boom (sine 120 -> 38 Hz, tau 0.16 s), a dull crack (low-passed
        # noise burst, tau 0.03 s) and a rolling rumble of band-passed noise around 700 Hz (tau 0.18 s)
        secs = float(parts[1]); n = int(secs * RATE); out = []; rnd = random.Random(3753)
        ph = 0.0; lp = 0.0; y1 = y2 = 0.0
        for i in range(n):
            t = i / RATE; att = min(1.0, t / 0.002)
            ph += (38 + 82 * math.exp(-t / 0.05)) / RATE; boom = math.sin(2 * math.pi * ph) * math.exp(-t / 0.16)
            x = rnd.random() * 2 - 1; lp = 0.55 * lp + 0.45 * x; crack = lp * math.exp(-t / 0.03)
            w = 2 * math.pi * 700 / RATE; q = 0.9
            y = x + 2 * q * math.cos(w) * y1 - q * q * y2; y2 = y1; y1 = y
            rumble = y * math.exp(-t / 0.18) * min(1.0, t / 0.01)
            out.append(att * (0.9 * boom + 0.35 * crack + 0.05 * rumble))
        return out
    if kind == "seekcharge2":
        # 'seekcharge2:f0:f1:seconds' -> Seeker Bolts charge-up v2 (2026-10-18; user: v1 'okay-ish', improve - powerful,
        # magical, no pings, no distortion): a warm rising tone f0 -> f1 (harmonics 1..6, gentle 1/k^1.8 rolloff, two voices
        # detuned +-4 cents), a sub-octave sine for weight, an orbit TREMOLO that speeds up 4 -> 20 Hz (the three orbs
        # spinning up) and pans nothing, an airy 'inhale' (noise through a resonant band-pass climbing 250 -> 3000 Hz, low
        # Q, so it rushes instead of whistling); crescendo (u^1.6) to full at the end, 30 ms attack, 12 ms cut (the launch
        # cue takes over on the same tick)
        f0, f1, secs = float(parts[1]), float(parts[2]), float(parts[3]); n = int(secs * RATE); out = []
        rnd = random.Random(3761); ph = [0.0, 0.0]; phs = 0.0; pp = 0.0; y1 = y2 = 0.0
        for i in range(n):
            u = i / n; f = f0 * (f1 / f0) ** (u ** 1.3)
            tone = 0.0
            for v, det in enumerate((1.0023, 0.9977)):
                ph[v] += f * det / RATE
                tone += sum(math.sin(2 * math.pi * k * ph[v]) / k ** 1.8 for k in range(1, 7))
            phs += 0.5 * f / RATE; sub = math.sin(2 * math.pi * phs)
            pp += (4 + 16 * u ** 1.4) / RATE; trem = 0.62 + 0.38 * (0.5 + 0.5 * math.sin(2 * math.pi * pp))
            fc = 250 * (3000 / 250) ** u; w = 2 * math.pi * fc / RATE; q = 0.86
            x = rnd.random() * 2 - 1; y = x + 2 * q * math.cos(w) * y1 - q * q * y2; y2 = y1; y1 = y
            env = (0.08 + 0.92 * u ** 1.6) * min(1.0, i / (0.03 * RATE)) * min(1.0, (n - i) / (0.012 * RATE))
            out.append(env * (0.22 * tone * trem + 0.30 * sub + 0.05 * y * (0.3 + 0.7 * u)))
        return out
    if kind == "seekzap":
        # 'seekzap:seconds:seed' -> an electric CRACKLE (Seeker Bolts v2 launch / hit): 30-40 short noise sparks (1-6 ms,
        # random gaps) through a band-pass at 1.6-3.5 kHz with LOW Q (a fizz, not a tone), denser and louder at the
        # start, decaying over the length; no sustained partials, so nothing pings
        secs, seed = float(parts[1]), int(parts[2]); n = int(secs * RATE); out = [0.0] * n; rnd = random.Random(seed)
        t = 0.0
        while t < secs:
            u = t / secs; L = int(rnd.uniform(0.001, 0.006) * RATE); a = (1 - u) ** 1.5 * rnd.uniform(0.5, 1.0)
            fc = rnd.uniform(1600, 3500); w = 2 * math.pi * fc / RATE; q = 0.7; y1 = y2 = 0.0; s0 = int(t * RATE)
            for j in range(L + int(0.004 * RATE)):
                x = (rnd.random() * 2 - 1) if j < L else 0.0
                y = x + 2 * q * math.cos(w) * y1 - q * q * y2; y2 = y1; y1 = y
                if s0 + j < n: out[s0 + j] += a * 0.5 * y
            t += rnd.uniform(0.004, 0.012) + 0.05 * u * u
        return out
    if kind == "purr":
        # 'purr:f0:seconds' -> Tame Animal (2026-10-18): a big cat's contented PURR - a low rumble (f0 ~ 26 Hz pulse
        # train of soft noise bursts through a ~260 Hz low-pass, with a faint f0*3 / f0*5 tonal body so it reads as a
        # voice, not wind), breathing in two cycles (inhale softer and slightly higher, exhale fuller), 150 ms attack,
        # dying away over the last 40 %
        f0, secs = float(parts[1]), float(parts[2]); n = int(secs * RATE); out = [0.0] * n; rnd = random.Random(2618)
        lp = lp2 = 0.0; a = 1 - math.exp(-2 * math.pi * 260 / RATE); ph = 0.0
        for i in range(n):
            t = i / RATE; u = t / secs
            breath = 0.5 + 0.5 * math.sin(2 * math.pi * (u * 2.0) - math.pi / 2)        # 2 breaths over the clip
            f = f0 * (1.0 + 0.08 * (1 - breath)); ph += f / RATE
            pulse = max(0.0, math.sin(2 * math.pi * ph)) ** 3                              # the purr's rapid pulses
            lp += a * ((rnd.random() * 2 - 1) - lp); lp2 += a * (lp - lp2)
            body = 0.35 * math.sin(2 * math.pi * 3 * ph) + 0.15 * math.sin(2 * math.pi * 5 * ph)
            env = min(1.0, t / 0.15) * (1.0 if u < 0.6 else max(0.0, 1 - (u - 0.6) / 0.4) ** 1.4) * (0.55 + 0.45 * breath)
            out[i] = env * pulse * (2.6 * lp2 + body)
        return out
    if kind == "bell":
        # 'bell:f0:seconds' -> a struck holy bell: inharmonic partials (1, 2.0, 2.76, 4.07, 5.4 x f0) each with its own
        # decay (higher = faster), 4 ms attack, slight detune shimmer
        f0, secs = float(parts[1]), float(parts[2])
        n = int(secs * RATE); out = []
        ratios = (1.0, 2.0, 2.76, 4.07, 5.4); gains = (1.0, 0.5, 0.45, 0.25, 0.15); decays = (1.0, 1.4, 1.9, 2.6, 3.4)
        ph = [0.0] * 5
        for i in range(n):
            t = i / RATE; u = i / n
            att = min(1.0, t / 0.004); v = 0.0
            for k in range(5):
                ph[k] += 2 * math.pi * f0 * ratios[k] * (1 + 0.0015 * math.sin(2 * math.pi * (1.3 + k) * t)) / RATE
                v += gains[k] * math.exp(-decays[k] * 2.2 * u) * math.sin(ph[k])
            out.append(att * 0.45 * v * (1 - u) ** 0.3)
        return out
    if kind == "beam":
        # 'beam:f0:seconds' -> a bright holy beam: f0 with its 2nd/3rd/4th harmonics, slow 4.5 Hz vibrato, a high
        # shimmer partial (f0*6) with 9 Hz tremolo, soft noise air; swells over the first 45 % then sustains and tails
        f0, secs = float(parts[1]), float(parts[2])
        n = int(secs * RATE); out = []; rnd = random.Random(5); lp = 0.0
        ph = [0.0] * 5; ratios = (1.0, 2.0, 3.0, 4.0, 6.0); gains = (1.0, 0.42, 0.18, 0.08, 0.10)      # v3: softer, fewer upper harmonics
        for i in range(n):
            t = i / RATE; u = i / n
            env = min(1.0, (u / 0.45) ** 1.6) if u < 0.45 else (1.0 if u < 0.8 else (1 - (u - 0.8) / 0.2) ** 1.2)
            vib = 1 + 0.006 * math.sin(2 * math.pi * 4.5 * t)
            v = 0.0
            for k in range(5):
                g = gains[k] * (0.6 + 0.4 * math.sin(2 * math.pi * 9 * t)) if k == 4 else gains[k]
                ph[k] += 2 * math.pi * f0 * ratios[k] * vib * (1 + 0.002 * k * math.sin(2 * math.pi * 0.9 * t)) / RATE
                v += g * math.sin(ph[k])
            lp = 0.9 * lp + 0.1 * (rnd.random() * 2 - 1)
            out.append(env * (0.38 * v + 0.14 * lp * env))
        return out
    if kind == "drone":
        f0, secs = float(parts[1]), float(parts[2])
        n = int(secs * RATE); out = []; rnd = random.Random(11); lp = 0.0; lp2 = 0.0
        ph = [0.0, 0.0, 0.0, 0.0]; ratios = (1.0, 1.19, 1.414, 2.0); gains = (1.0, 0.55, 0.7, 0.3)
        for i in range(n):
            t = i / RATE; u = i / n
            env = min(1.0, t / 0.08) * (1 - u) ** 1.4
            trem = 0.75 + 0.25 * math.sin(2 * math.pi * 5.5 * t)
            glide = 1.0 - 0.12 * u                                   # slowly sinks
            v = 0.0
            for k in range(4):
                ph[k] += 2 * math.pi * f0 * ratios[k] * glide * (1 + 0.004 * math.sin(2 * math.pi * (0.7 + k) * t)) / RATE
                v += gains[k] * math.sin(ph[k])
            lp = 0.96 * lp + 0.04 * (rnd.random() * 2 - 1); lp2 = 0.9 * lp2 + 0.1 * lp
            swell = math.sin(math.pi * min(1.0, u / 0.6)) if u < 0.6 else (1 - u) / 0.4
            out.append(env * (0.45 * v * trem + 1.8 * lp2 * swell))
        return out
    f0, f1, secs = float(parts[1]), float(parts[2]), float(parts[3])
    n = int(secs * RATE); out = []; ph = 0.0; ph2 = 0.0; rnd = random.Random(7); lp = 0.0
    for i in range(n):
        t = i / RATE; u = i / n
        f = f0 * (f1 / f0) ** u * (1 + 0.03 * math.sin(2 * math.pi * 6 * t))
        ph += 2 * math.pi * f / RATE; ph2 += 2 * math.pi * 2 * f / RATE
        env = min(1.0, t / 0.06) * (1 - u) ** 0.6
        lp = 0.92 * lp + 0.08 * (rnd.random() * 2 - 1)                  # cheap low-passed noise
        out.append(env * (0.75 * math.sin(ph) + 0.25 * math.sin(ph2) + 0.35 * lp))
    return out


def load_mono(path):
    """-> (rate, list of float samples in -1..1, mono)."""
    w = wave.open(path, "rb")
    ch, sw, rate, n = w.getnchannels(), w.getsampwidth(), w.getframerate(), w.getnframes()
    raw = w.readframes(n); w.close()
    if sw == 2:
        a = array.array("h"); a.frombytes(raw); s = [x / 32768.0 for x in a]
    elif sw == 1:
        s = [(x - 128) / 128.0 for x in raw]
    elif sw == 3:
        s = [int.from_bytes(raw[i:i + 3], "little", signed=True) / 8388608.0 for i in range(0, len(raw) - 2, 3)]
    else:
        raise ValueError("unsupported sample width %d in %s" % (sw, path))
    if ch > 1:
        s = [sum(s[i:i + ch]) / ch for i in range(0, len(s) - ch + 1, ch)]
    return rate, s


def resample(s, src, dst):
    if abs(src - dst) < 1e-6: return list(s)
    n = int(len(s) * dst / src); out = []
    for i in range(n):
        x = i * src / dst; j = int(x); f = x - j
        a = s[j]; b = s[j + 1] if j + 1 < len(s) else a
        out.append(a + (b - a) * f)
    return out


def mix(layers, drive=1.0, swell=0.0, swell_out=0.0):
    tracks = []
    for layer in layers:
        rel, gain, start, maxlen, fade = layer[:5]
        speed = layer[5] if len(layer) > 5 else 1.0
        fade_in = layer[6] if len(layer) > 6 else 0.0                  # 7th value = fade-in seconds (v4)
        if rel.startswith("synth:"):
            s = synth(rel[6:])
        else:
            rate, s = load_mono(os.path.join(SFX, rel))
            if len(layer) > 7 and layer[7]: s = s[int(layer[7] * rate):]   # 8th value = source offset in seconds (2026-10-16: slice a sample)
            s = resample(s, rate * abs(speed), RATE)                # speed > 1 = higher pitch, shorter
            if speed < 0: s = s[::-1]                               # negative speed = REVERSED (2026-10-14)
        if maxlen is not None: s = s[-int(maxlen * RATE):] if speed < 0 else s[:int(maxlen * RATE)]   # a reversed layer keeps its TAIL (the peak)
        if fade > 0:
            nf = min(int(fade * RATE), len(s))
            fpow = layer[8] if len(layer) > 8 else 1.0                  # 9th value = fade-out curve (2026-10-16): > 1 drops fast, then tails off smoothly
            for i in range(nf):
                s[len(s) - nf + i] *= (1 - i / nf) ** fpow
        if fade_in > 0:
            nf = min(int(fade_in * RATE), len(s))
            for i in range(nf):
                s[i] *= i / nf
        tracks.append((int(start * RATE), [x * gain for x in s]))
    total = max(o + len(s) for o, s in tracks)
    out = [0.0] * total
    for o, s in tracks:
        for i, x in enumerate(s): out[o + i] += x
    peak = max(abs(x) for x in out) or 1.0
    if drive != 1.0:
        out = [math.tanh(x / peak * drive) for x in out]                 # soft-clipped, denser and louder
        peak = max(abs(x) for x in out) or 1.0
    g = (10 ** (-1 / 20)) / peak if peak > 10 ** (-1 / 20) else 1.0
    if swell > 0:                                                       # whole-mix swell from silence (v6)
        nf = min(int(swell * RATE), len(out))
        for i in range(nf): out[i] *= (i / nf) ** 1.5
    if swell_out > 0:                                                   # whole-mix fade-out to silence (2026-10-16)
        nf = min(int(swell_out * RATE), len(out))
        for i in range(nf): out[len(out) - 1 - i] *= (i / nf) ** 1.3
    return [x * g for x in out], peak


def write_wav(path, s):
    a = array.array("h", [max(-32768, min(32767, int(round(x * 32767)))) for x in s])
    w = wave.open(path, "wb"); w.setnchannels(1); w.setsampwidth(2); w.setframerate(RATE); w.writeframes(a.tobytes()); w.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--revert", action="store_true")
    a = ap.parse_args()
    if a.revert:
        for name in list(MIXES) + OLD_FILES:
            p = os.path.join(OUTDIR, name)
            if os.path.exists(p): os.remove(p); print("deleted", p)
        return 0
    for name, layers in MIXES.items():
        s, peak = mix(layers, DRIVE.get(name, 1.0), FADE_IN.get(name, 0.0), FADE_OUT.get(name, 0.0))
        if name in TAIL: s = add_tail(s, *TAIL[name])
        print("%-22s %.2fs  peak before normalise %.2f  layers: %s" % (name, len(s) / RATE, peak, ", ".join("%s x%.2f @%.2fs" % (l[0], l[1], l[2]) for l in layers)))
        if a.apply:
            write_wav(os.path.join(OUTDIR, name), s); print("   written", os.path.join(OUTDIR, name))
    if a.apply:
        for name in OLD_FILES:
            p = os.path.join(OUTDIR, name)
            if os.path.exists(p): os.remove(p); print("   removed stale", p)
    if not a.apply: print("Dry run OK - rerun with --apply (or --revert).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
