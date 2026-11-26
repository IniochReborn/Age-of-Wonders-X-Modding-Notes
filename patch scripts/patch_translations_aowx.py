"""
patch_translations_aowx.py - refresh the German/French/Italian/Spanish text for
the strings AoWx renamed from vanilla.

Background
----------
AoWx renames things by filling the *English* column of the Multilizer
dictionaries (Dict\\*.mld) while leaving the `Original` column alone, because
`Original` is the lookup key the game matches against. The consequence is that
the four foreign columns still describe the VANILLA thing: "Dragon Slaying" is
still "Drachentöten" even though the ability is now "Monster Slaying".

This script updates only those entries. Translations that are merely poor are
left alone, per the project's translation policy. Entries where AoWx only fixed
an English typo or spacing ("Undergroud" -> "Underground", "SouthEast" ->
"South East") are deliberately NOT touched, because the foreign text was
already correct.

Usage
-----
    python patch_translations_aowx.py            dry run (default)
    python patch_translations_aowx.py --apply    write, after backing up
    python patch_translations_aowx.py --revert   restore from the backup
"""
import os, sys, shutil

HERE = os.path.dirname(os.path.abspath(__file__))
GAME = os.path.abspath(os.path.join(HERE, ".."))
DICT = os.path.join(GAME, "Dict")
BACKUP = os.path.join(GAME, "backup", "Dict.bak_translations")

# the MLD codec lives with the research artifacts
for cand in (os.path.join(GAME, "modding tools", "aowxlib"),
             os.path.join(GAME, "old modding tools", "research")):
    if cand not in sys.path:
        sys.path.insert(0, cand)
try:
    from mld import MLDFile
except ImportError:
    sys.exit("mld.py not found - expected in 'modding tools\\aowxlib' or "
             "'old modding tools\\research'")

DE, FR, IT, ES = 1, 2, 3, 4          # translation column indices

# (file, record index, expected Original, {column: new text})
PATCHES = [
    # ---- title rename: Age of Wonders -> Age of Wonders X ----
    ("AoWSetup", 0, "Age of Wonders", {
        DE: "Age of Wonders X", FR: "Age of Wonders X",
        IT: "Age of Wonders X", ES: "Age of Wonders X"}),
    ("ResStr", 121, "Age of Wonders", {
        DE: "Age of Wonders X", FR: "Age of Wonders X",
        IT: "Age of Wonders X", ES: "Age of Wonders X"}),
    ("ResStr", 122, "Age of Wonders email game", {
        DE: "Age of Wonders X Email-Spiel",
        FR: "Partie e-mail d'Age of Wonders X",
        IT: "Partita Age of Wonders X via e-mail",
        ES: "Partida de Age of Wonders X por correo-e"}),
    ("ResStr", 123, "Age Of Wonders is already running", {
        DE: "Age Of Wonders X läuft bereits",
        FR: "Age of Wonders X est déjà actif",
        IT: "Age Of Wonders X è già in esecuzione",
        ES: "Age Of Wonders X ya está funcionando"}),
    ("ResStr", 124, "Age Of Wonders Map", {
        DE: "Age Of Wonders X-Karte",
        FR: "Carte d'Age of Wonders X",
        IT: "Mappa di Age Of Wonders X",
        ES: "Mapa de Age Of Wonders X"}),

    # ---- ability / term renames ----
    ("ResStr", 385, "Dragon", {
        DE: "Monster", FR: "Monstre", IT: "Mostro", ES: "Monstruo"}),
    ("ResStr", 386, "Dragon Slaying", {
        DE: "Monstertöten", FR: "Chasse aux monstres",
        IT: "Ammazzare mostri", ES: "Matar monstruos"}),
    ("Release", 248, "Enhanced attack ability against dragonkind.", {
        DE: "Erhöhte Angriffsfähigkeit gegen monströse Einheiten: "
            "Angriff (+3) und Schaden (+3).",
        FR: "Meilleure capacité d'attaque contre les unités monstrueuses : "
            "Attaque (+3) et Dommages (+3).",
        IT: "Potenzia la caratteristica attacco contro le unità mostruose: "
            "Attacco (+3) e Danno (+3).",
        ES: "Mejora la capacidad de ataque contra las unidades monstruosas: "
            "ataque (+3) y daños (+3)."}),
    ("ResStr", 462, "Flame Throwing", {
        DE: "Kosmischer Atem", FR: "Souffle cosmique",
        IT: "Soffio cosmico", ES: "Aliento cósmico"}),
    ("ResStr", 864, "Rejuvenate", {
        DE: "Land verbrennen", FR: "Terre brûlée",
        IT: "Bruciare il terreno", ES: "Calcinar el terreno"}),
    ("ResStr", 932, "Shoot Black Javelin", {
        DE: "Suchende Bolzen", FR: "Carreaux chercheurs",
        IT: "Dardi cercatori", ES: "Virotes buscadores"}),
    ("ResStr", 942, "Slow", {
        DE: "Zeichen des Jägers", FR: "Marque du chasseur",
        IT: "Marchio del cacciatore", ES: "Marca del cazador"}),
    ("Release", 352, "Halves the target's mobility for the duration of combat.", {
        DE: "Das Ziel wird als Beute markiert und ist leichter zu treffen: "
            "Verteidigung (-1) und Widerstand (-1).",
        FR: "La cible est marquée comme proie, ce qui la rend plus facile "
            "à frapper : Défense (-1) et Résistance (-1).",
        IT: "Il bersaglio viene marchiato come preda, diventando più facile "
            "da colpire: Difesa (-1) e Resistenza (-1).",
        ES: "El objetivo queda marcado como presa, lo que facilita golpearlo: "
            "defensa (-1) y resistencia (-1)."}),
    ("ResStr", 996, "Summon Mermaid", {
        DE: "Geist herbeirufen", FR: "Invocation de l'esprit",
        IT: "Evocare spirito", ES: "Invocar espíritu"}),

    # ---- campaign-select screen, repurposed by AoWx ----
    ("ResStr", 254, "Choose a Faction", {
        DE: "Kampagne wählen", FR: "Choisir une campagne",
        IT: "Scegliere una campagna", ES: "Elegir una campaña"}),
    ("AoW", 983, "The Cult of Storms", {
        DE: "Herausforderungsmodus", FR: "Mode défi",
        IT: "Modalità sfida", ES: "Modo desafío"}),
    ("ResStr", 1019, "The Cult of Storms", {
        DE: "Herausforderungsmodus", FR: "Mode défi",
        IT: "Modalità sfida", ES: "Modo desafío"}),
    ("AoW", 988, "The Keepers", {
        DE: "Aus menschlicher Sicht", FR: "Une perspective humaine",
        IT: "Una prospettiva umana", ES: "Una perspectiva humana"}),
    ("ResStr", 1022, "The Keepers", {
        DE: "Aus menschlicher Sicht", FR: "Une perspective humaine",
        IT: "Una prospettiva umana", ES: "Una perspectiva humana"}),
    ("AoW", 12, "· Accept the Humans and their presence.", {
        DE: "Alle Menschen für eine gemeinsame Sache vereinen.",
        FR: "Unir tous les Humains autour d'une cause commune.",
        IT: "Unire tutti gli Umani per una causa comune.",
        ES: "Unir a todos los humanos en una causa común."}),
    ("AoW", 13, "· Actively oppose the Cult of Storms.", {
        DE: "Menschliche Siedlungen vor dem Kult der Stürme schützen.",
        FR: "Défendre les colonies humaines contre le Culte des Tempêtes.",
        IT: "Difendere gli insediamenti umani dal Culto della Tempesta.",
        ES: "Defender los asentamientos humanos del culto de las tormentas."}),
    ("AoW", 15, "· Preserve harmony over the earth and its inhabitants.", {
        DE: "Das Vertrauen der Wächter zurückgewinnen.",
        FR: "Regagner la confiance des Gardiens.",
        IT: "Riconquistare la fiducia dei Guardiani.",
        ES: "Recuperar la confianza de los custodios."}),
    ("AoW", 16, "· Rebuild the Elven Court in the Valley of Storms.", {
        DE: "Stellen Sie im ersten Szenario Ihre Armee und Ausrüstung zusammen.",
        FR: "Personnalise ton armée et ton inventaire dans le premier scénario.",
        IT: "Personalizzate il vostro esercito e il vostro inventario nel primo scenario.",
        ES: "Personaliza tu ejército y tu inventario en el primer escenario."}),
    ("AoW", 17, "· Restore order under their own law and power.", {
        DE: "Können Sie es mit der Gruppe der Drei aufnehmen?",
        FR: "Peux-tu espérer défier le Groupe des Trois ?",
        IT: "Potete sperare di sfidare il Gruppo dei Tre?",
        ES: "¿Puedes aspirar a desafiar al Grupo de los Tres?"}),
    ("AoW", 18, "· Resurrect the greatest Elven Lord, Inioch.", {
        DE: "Kämpfen Sie sich durch eine Reihe schwieriger Schlachten.",
        FR: "Fraye-toi un chemin à travers une série de batailles difficiles.",
        IT: "Fatevi strada attraverso una serie di battaglie difficili.",
        ES: "Ábrete paso a través de una serie de batallas difíciles."}),
    ("AoW", 19, "· Rid the world of both the Humans and Keepers.", {
        DE: "Sind Sie der beste Age of Wonders-Spieler?",
        FR: "Es-tu le meilleur joueur d'Age of Wonders ?",
        IT: "Siete il miglior giocatore di Age of Wonders?",
        ES: "¿Eres el mejor jugador de Age of Wonders?"}),
]

# substring edits inside long tutorial texts (AoWx dropped the boat, renamed the game)
SUBS = [
    ("CustMaps", 1, {
        DE: [("Als Belohnung trifft ein Boot mit Verstärkung für Sie ein.",
              "Als Belohnung trifft Verstärkung für Sie ein.")],
        FR: [("l'arrivée de ce bateau rempli de renforts", "l'arrivée de renforts")],
        IT: [("l'arrivo di una barca carica di rinforzi", "l'arrivo di rinforzi")],
        ES: [("la llegada de un barco cargado de refuerzos", "la llegada de refuerzos")],
    }),
    ("CustMaps", 1065, {
        DE: [("durch die grundlegenden Optionen in \"Age of Wonders\"",
              "durch das grundlegende Spielgeschehen von \"Age of Wonders X\"")],
        FR: [("avec les options de base d'Age of Wonders",
              "avec les mécanismes de base d'Age of Wonders X")],
        IT: [("attraverso le opzioni di base di Age of Wonder",
              "attraverso le meccaniche di base di Age of Wonders X")],
        ES: [("las opciones básicas de Age of Wonders",
              "la jugabilidad básica de Age of Wonders X")],
    }),
]

LANGNAME = {DE: "de", FR: "fr", IT: "it", ES: "es"}


def enc(s):
    # French typography wants a non-breaking space before ':' and '?', but the
    # game draws text with bitmap glyph strips and stock French uses 0 of them
    # across 6620 cells - 0xA0 would index whatever glyph sits in that cell.
    # Normalise to plain spaces, and refuse anything cp1252 cannot hold.
    s = s.replace(" ", " ").replace(" ", " ")
    for ch in ("’", "‘"):
        s = s.replace(ch, "'")
    for ch in ("“", "”"):
        s = s.replace(ch, '"')
    s = s.replace("–", "-").replace("—", "-").replace("…", "...")
    return s.encode("cp1252")


def dec(b):
    return b.decode("cp1252", "replace") if isinstance(b, (bytes, bytearray)) else b


def group(items):
    out = {}
    for entry in items:
        out.setdefault(entry[0], []).append(entry)
    return out


def run(apply_it):
    changed_total = 0
    problems = []
    files = sorted(set([p[0] for p in PATCHES] + [s[0] for s in SUBS]))
    for name in files:
        path = os.path.join(DICT, name + ".mld")
        before = open(path, "rb").read()
        m = MLDFile.load(path)
        n_before = len(m.records)
        touched = {}

        for _f, idx, expect, cols in [p for p in PATCHES if p[0] == name]:
            rec = m.records[idx]
            if dec(rec.Original) != expect:
                problems.append("%s#%d Original is %r, expected %r"
                                % (name, idx, dec(rec.Original)[:60], expect[:60]))
                continue
            for col, text in cols.items():
                old = dec(rec.translations[col])
                if old == text:
                    continue
                print("  %s#%-5d %s  %r\n        -> %r" % (name, idx, LANGNAME[col],
                                                           old[:70], text[:70]))
                if apply_it:
                    rec.translations[col] = enc(text)
                touched.setdefault(idx, set()).add(col)
                changed_total += 1

        for _f, idx, cols in [s for s in SUBS if s[0] == name]:
            rec = m.records[idx]
            for col, pairs in cols.items():
                cur = dec(rec.translations[col])
                new = cur
                for find, repl in pairs:
                    if find not in new:
                        problems.append("%s#%d %s: phrase not found %r"
                                        % (name, idx, LANGNAME[col], find[:50]))
                        continue
                    new = new.replace(find, repl)
                if new != cur:
                    print("  %s#%-5d %s  ...%s..." % (name, idx, LANGNAME[col],
                                                      pairs[0][1][:60]))
                    if apply_it:
                        rec.translations[col] = enc(new)
                    touched.setdefault(idx, set()).add(col)
                    changed_total += 1

        if apply_it and touched:
            m.save(path)
            after = MLDFile.load(path)
            # safety net: nothing except the intended cells may differ
            base = MLDFile.parse(before)
            assert len(after.records) == n_before, "record count changed in " + name
            for i, (a, b) in enumerate(zip(after.records, base.records)):
                assert a.Original == b.Original, "Original changed at %s#%d" % (name, i)
                for c in range(len(a.translations)):
                    if a.translations[c] != b.translations[c]:
                        if c not in touched.get(i, set()):
                            raise AssertionError("unintended change %s#%d col %d" % (name, i, c))
            print("  [%s] saved, %d cell(s) changed, all other text verified unchanged"
                  % (name, sum(len(v) for v in touched.values())))

    print("\n%d translation cell(s) %s" % (changed_total, "updated" if apply_it else "would change"))
    if problems:
        print("\nPROBLEMS (%d):" % len(problems))
        for p in problems:
            print("   " + p)
    return len(problems) == 0


def backup():
    if os.path.isdir(BACKUP):
        print("backup already exists: %s" % BACKUP)
        return
    os.makedirs(os.path.dirname(BACKUP), exist_ok=True)
    shutil.copytree(DICT, BACKUP)
    print("backed up Dict -> %s" % BACKUP)


def revert():
    if not os.path.isdir(BACKUP):
        sys.exit("no backup at %s" % BACKUP)
    for f in os.listdir(BACKUP):
        shutil.copy2(os.path.join(BACKUP, f), os.path.join(DICT, f))
    print("restored %d file(s) from %s" % (len(os.listdir(BACKUP)), BACKUP))


if __name__ == "__main__":
    if "--revert" in sys.argv:
        revert()
    elif "--apply" in sys.argv:
        backup()
        ok = run(True)
        sys.exit(0 if ok else 1)
    else:
        print("DRY RUN - nothing written. Use --apply to write.\n")
        ok = run(False)
        sys.exit(0 if ok else 1)
