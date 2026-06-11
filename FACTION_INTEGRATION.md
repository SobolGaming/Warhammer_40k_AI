# Faction Integration Plan

This document defines the Phase 17 faction-content rollout. CORE V2 remains an
11th Edition-only engine. Prior-edition Wahapedia data is bridge source
material: it is normalized, patched by official 11th Edition transition
instructions, and then compiled into 11th Edition catalog records.

## Integration Contract

- Do not import a prior-edition catalog into runtime engine code.
- Keep the raw Wahapedia mirror immutable and source-linked.
- Represent every official 11th Edition transition instruction as an ordered
  patch operation.
- Emit explicit unsupported diagnostics for rule text, targets, or source rows
  that cannot be represented safely.
- Runtime descriptors consume structured catalog data, never raw rule text or
  HTML.
- Faction PRs must keep the same UI, headless, network, replay, and test decision
  path.
- Do not mark a faction phase complete while unapproved unsupported descriptors
  remain for matched-play content in that phase.

## Queue Source

The seeded detachment queue is derived from:

- package ID: `gw-11e-faction-detachments-2026-27`
- path:
  `src/warhammer40k_core/rules/source_packages/warhammer_40000_11th/faction_detachments_2026_27.py`
- source title: `Warhammer 40,000 11th Edition Faction Detachments 2026-27`
- source version: `2026-27`
- source date: `2026-06-11`
- upstream identity: `official-11th-edition-faction-detachment-source-package`
- source edition: `11th`
- schema version: `core-v2-faction-detachment-source-v1`
- source-payload SHA-256 checksum:
  `5e48d00f5d670b60a9ef78902772e6cd6fed95f5f6ab8ad3e27bea4e5bd5ff89`

Queue refreshes must be generated from this package, not hand-edited, except for
explicitly reviewed corrections recorded in the patch package manifest. Until a
dedicated generator lands in Phase 17A, queue verification and checksum
refreshes use the package API:

```bash
uv run python - <<'PY'
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    faction_detachments_2026_27 as source,
)

print(source.source_package_identity_payload())
for row in source.detachment_rows():
    print(f"{row.faction_id}\t{row.name}")
PY
```

Names in this queue preserve upstream source-row spelling exactly, including any
official misspellings. Corrections must be represented as source-linked patch operations,
not silent edits. The current source package intentionally preserves
`Auxillary Cadre` and `Brood Brothers Auxillia` because those are the exact
source-row names in the seeded package at source IDs
`gw-11e-faction-detachments-2026-27:detachment:tau-empire:auxillary-cadre` and
`gw-11e-faction-detachments-2026-27:detachment:genestealer-cults:brood-brothers-auxillia`.

## Faction Phase Shape

Large phases are faction names. Lettered subphases inside a faction are named
content slices: exact detachment support, exact datasheet support, exact
enhancement/Stratagem support when tied to a detachment, or a tightly coupled
official patch batch such as a named FRAME keyword update.

Each faction has an unlettered intake gate before lettered work starts:

1. Mirror and normalize the faction's prior-edition Wahapedia source rows.
2. Add official 11th Edition transition patch records for the faction.
3. Generate a source coverage report for army rules, detachments, enhancements,
   Stratagems, datasheets, wargear, weapon profiles, base sizes, and FAQs.
4. Expand the faction's lettered subphases from exact source row names.

Lettered subphases should be small enough for review. Prefer one detachment or
one datasheet per subphase unless several datasheets share one inseparable kit,
weapon profile set, or official patch operation.

## Pilot Phase: Death Guard

Death Guard is the pilot because the available official update example exercises
army rules, detachment content, datasheet abilities, keywords, weapon
characteristics, and FAQ advisory records.

- Phase Death Guard A: Nurgle's Gift army rule transition patch, including
  Contagion Range cap and Skullsquirm Blight replacement.
- Phase Death Guard B: Tallyband Summoners detachment support, including
  Beckoning Blight enhancement replacement.
- Phase Death Guard C: Typhus datasheet support, including Eater Plague
  replacement.
- Phase Death Guard D: Deathshroud Terminators datasheet support, including
  Death Approaches replacement.
- Phase Death Guard E: Chaos Predator Destructor datasheet support, including
  Predator Autocannon Strength replacement.
- Phase Death Guard F: FRAME keyword patch batch for Chaos Land Raider, Chaos
  Predator Annihilator, Chaos Predator Destructor, Chaos Rhino, Miasmic
  Malignifier, and Plagueburst Crawler.
- Phase Death Guard G: Plagueburst Crawler FAQ advisory record for Spore-laced
  Shock Waves, classified as `advisory_only` unless source review determines it
  changes executable behavior.
- Phase Death Guard H+: Remaining Death Guard datasheets, one exact datasheet or
  source-coupled kit group per lettered subphase after source import.

## FAQ Classification Gate

Every FAQ row in a faction intake or lettered subphase must be classified before
catalog emission as exactly one of:

- `advisory_only`: source-linked note that does not change executable behavior.
- `executable_patch`: source-linked patch operation represented by supported
  descriptors or catalog records in the same phase.
- `unsupported_executable_change`: source-linked executable behavior change that
  remains blocked behind an explicit unsupported diagnostic until implemented.

FAQs that change gameplay semantics must not be stored as `advisory_only`.
Reclassification requires a source-linked patch operation or diagnostic update.

## Faction Phase Queue

The queue starts with the pilot, then proceeds through factions already seeded in
the current 11th Edition faction-detachment source package, then fills missing
Imperial factions from the patched Wahapedia bridge source.

### Phase Death Guard

Initial letters are defined in the pilot phase. Remaining letters cover exact
Death Guard datasheet rows from the patched source mirror.

### Phase Orks

- Detachment letters: More Dakka!, Rollin' Deff, Taktikal Brigade, Blitz
  Brigade, Bully Boyz, Da Big Hunt, Dread Mob, Freebooter Krew, Green Tide, Kult
  of Speed, Speedwaaagh!, War Horde.
- Datasheet letters: exact Orks datasheet rows from the patched source mirror,
  one datasheet or source-coupled kit group per letter.

### Phase Aeldari

- Detachment letters: Armoured Warhost, Fateful Performance, Path of the
  Outcast, Twilight Flickers, Aspect Host, Corsair Coterie, Devoted of Ynnead,
  Eldritch Raiders, Ghosts of the Webway, Guardian Battlehost, Seer Council,
  Serpent's Brood, Spirit Conclave, Warhost, Windrider Host.
- Datasheet letters: exact Aeldari datasheet rows from the patched source mirror,
  one datasheet or source-coupled kit group per letter.

### Phase Drukhari

- Detachment letters: Exhibition of Slaughter, Kabalite Agonysts, Tools of
  Torment, Covenite Coterie, Kabalite Cartel, Realspace Raiders, Reaper's Wager,
  Skysplinter Assault, Spectacle of Spite.
- Datasheet letters: exact Drukhari datasheet rows from the patched source
  mirror, one datasheet or source-coupled kit group per letter.

### Phase Tyranids

- Detachment letters: Ambush Predators, Talons of the Norn Queen, Warrior
  Bioform Onslaught, Assimilation Swarm, Crusher Stampede, Invasion Fleet,
  Subterranean Assault, Synaptic Nexus, Unending Swarm, Vanguard Onslaught.
- Datasheet letters: exact Tyranids datasheet rows from the patched source
  mirror, one datasheet or source-coupled kit group per letter.

### Phase Genestealer Cults

- Detachment letters: Heroes of the Uprising, Purestrain Broodswarm, Xenocult
  Masses, Biosanctic Broodsurge, Brood Brothers Auxillia, Final Day, Host of
  Ascension, Outlander Claw, Xenocreed Congregation.
- Datasheet letters: exact Genestealer Cults datasheet rows from the patched
  source mirror, one datasheet or source-coupled kit group per letter.

### Phase Necrons

- Detachment letters: Hand of the Dynasty, Skyshroud Spearhead, The Phaeron's
  Armoury, Annihilation Legion, Awakened Dynasty, Canoptek Court, Cryptek
  Conclave, Cursed Legion, Hypercrypt Legion, Obeisance Phalanx, Pantheon of
  Woe, Starshatter Arsenal.
- Datasheet letters: exact Necrons datasheet rows from the patched source mirror,
  one datasheet or source-coupled kit group per letter.

### Phase Leagues of Votann

- Detachment letters: Armoured Trailblazers, Farseekers, Hearthguard Covenant,
  Brandfast Oathband, Dalve Assault Shift, Hearthband, Hearthfyre Arsenal,
  Mercenary Oathband, Needgaard Oathband, Persecution Prospect.
- Datasheet letters: exact Leagues of Votann datasheet rows from the patched
  source mirror, one datasheet or source-coupled kit group per letter.

### Phase Tau Empire

- Detachment letters: Advanced Acquisition Cadre, Auxillary Cadre, Experimental
  Prototype Cadre, Kauyon, Kroot Hunting Pack, Mont'ka, Retaliation Cadre.
- Datasheet letters: exact Tau Empire datasheet rows from the patched source
  mirror, one datasheet or source-coupled kit group per letter.

### Phase Space Marines

- Detachment letters: Fulguris Task Force, Librarius Conclave, Subversion Assets,
  1st Company Task Force, Anvil Siege Force, Armoured Speartip, Bastion Task
  Force, Blade of Ultramar, Ceramite Sentinels, Emperor's Shield, Firestorm
  Assault Force, Forgefather's Seekers, Gladius Task Force, Hammer of Avernii,
  Headhunter Task Force, Ironstorm Spearhead, Orbital Assault Force, Reclamation
  Force, Shadowmark Talon, Spearpoint Task Force, Stormlance Task Force,
  Vanguard Spearhead.
- Datasheet letters: exact Space Marines datasheet rows from the patched source
  mirror, one datasheet or source-coupled kit group per letter.

### Phase Dark Angels

- Detachment letters: Dark Age Arsenal, Darkflight Pursuit, Interrogation
  Conclave, Company of Hunters, Inner Circle Task Force, Lion's Blade Task
  Force, Unforgiven Task Force, Wrath of the Rock.
- Datasheet letters: exact Dark Angels datasheet rows from the patched source
  mirror, one datasheet or source-coupled kit group per letter.

### Phase Blood Angels

- Detachment letters: Encarmine Speartip, Legacy of Grace, Wrath of the Doomed,
  Angelic Inheritors, Liberator Assault Group, Rage-cursed Onslaught, The
  Angelic Host, The Lost Brethren.
- Datasheet letters: exact Blood Angels datasheet rows from the patched source
  mirror, one datasheet or source-coupled kit group per letter.

### Phase Space Wolves

- Detachment letters: Champions of Fenris, Legends of Saga and Song, Veterans of
  the Fang, Saga of the Beastslayer, Saga of the Bold, Saga of the Great Wolf,
  Saga of the Hunter.
- Datasheet letters: exact Space Wolves datasheet rows from the patched source
  mirror, one datasheet or source-coupled kit group per letter.

### Phase Black Templars

- Detachment letters: Marshal's Household, The Living Miracle, Wrathful
  Procession, Companions of Vehemence, Godhammer Assault Force, Vindication Task
  Force.
- Datasheet letters: exact Black Templars datasheet rows from the patched source
  mirror, one datasheet or source-coupled kit group per letter.

### Phase Deathwatch

- Detachment letters: Black Spear Task Force, plus any official 11th Edition
  transition detachments imported from source rows.
- Datasheet letters: exact Deathwatch datasheet rows from the patched source
  mirror, one datasheet or source-coupled kit group per letter.

### Phase Grey Knights

- Detachment letters: Argent Assault, Fires of Purgation, Immaterial
  Interdiction, Augurium Task Force, Banishers, Brotherhood Strike, Hallowed
  Conclave, Sanctic Spearhead, Warpbane Task Force.
- Datasheet letters: exact Grey Knights datasheet rows from the patched source
  mirror, one datasheet or source-coupled kit group per letter.

### Phase Chaos Space Marines

- Detachment letters: Cabal of Chaos, Devotees of Destruction, Murdertalon
  Raiders, Chaos Cult, Creations of Bile, Cult of the Arkifane, Deceptors, Dread
  Talons, Fellhammer Siege-host, Huron's Marauders, Nightmare Hunt, Pactbound
  Zealots, Renegade Raiders, Renegade Warband, Soulforged Warpack, Veterans of
  the Long War, Warpstrike Champions.
- Datasheet letters: exact Chaos Space Marines datasheet rows from the patched
  source mirror, one datasheet or source-coupled kit group per letter.

### Phase World Eaters

- Detachment letters: Butchers of Khorne, Brazen Engines, Vessels of Wrath,
  Berzerker Warband, Cult of Blood, Goretrack Onslaught, Khorne Daemonkin,
  Possessed Slaughterband.
- Datasheet letters: exact World Eaters datasheet rows from the patched source
  mirror, one datasheet or source-coupled kit group per letter.

### Phase Emperor's Children

- Detachment letters: Elegant Brutes, Frenzied Host, Spectacle of Slaughter,
  Carnival of Excess, Coterie of the Conceited, Court of the Phoenician,
  Mercurial Host, Peerless Bladesmen, Rapid Evisceration, Slaanesh's Chosen.
- Datasheet letters: exact Emperor's Children datasheet rows from the patched
  source mirror, one datasheet or source-coupled kit group per letter.

### Phase Thousand Sons

- Detachment letters: Ritual of Regeneration, Sekhetar Cohort, Servants of
  Change, Changehost of Deceit, Grand Coven, Hexwarp Thrallband, Rubricae
  Phalanx, Warpforged Cabal, Warpmeld Pact.
- Datasheet letters: exact Thousand Sons datasheet rows from the patched source
  mirror, one datasheet or source-coupled kit group per letter.

### Phase Chaos Knights

- Detachment letters: Bastions of Tyranny, Hunting Warpack, Iconoclast Fiefdom,
  Helhunt Lance, Houndpack Lance, Infernal Lance, Lords of Dread, Traitoris
  Lance.
- Datasheet letters: exact Chaos Knights datasheet rows from the patched source
  mirror, one datasheet or source-coupled kit group per letter.

### Phase Chaos Daemons

- Detachment letters: Cavalcade of Chaos, Lords of the Warp, Warptide, Blood
  Legion, Daemonic Incursion, Legion of Excess, Plague Legion, Scintillating
  Legion, Shadow Legion.
- Datasheet letters: exact Chaos Daemons datasheet rows from the patched source
  mirror, one datasheet or source-coupled kit group per letter.

### Phase Adepta Sororitas

- Detachment letters: exact Adepta Sororitas detachments from the patched source
  mirror and official transition package.
- Datasheet letters: exact Adepta Sororitas datasheet rows from the patched
  source mirror, one datasheet or source-coupled kit group per letter.

### Phase Adeptus Custodes

- Detachment letters: exact Adeptus Custodes detachments from the patched source
  mirror and official transition package.
- Datasheet letters: exact Adeptus Custodes datasheet rows from the patched
  source mirror, one datasheet or source-coupled kit group per letter.

### Phase Adeptus Mechanicus

- Detachment letters: exact Adeptus Mechanicus detachments from the patched
  source mirror and official transition package.
- Datasheet letters: exact Adeptus Mechanicus datasheet rows from the patched
  source mirror, one datasheet or source-coupled kit group per letter.

### Phase Astra Militarum

- Detachment letters: exact Astra Militarum detachments from the patched source
  mirror and official transition package.
- Datasheet letters: exact Astra Militarum datasheet rows from the patched source
  mirror, one datasheet or source-coupled kit group per letter.

### Phase Imperial Agents

- Detachment letters: exact Imperial Agents detachments from the patched source
  mirror and official transition package.
- Datasheet letters: exact Imperial Agents datasheet rows from the patched
  source mirror, one datasheet or source-coupled kit group per letter.

### Phase Imperial Knights

- Detachment letters: exact Imperial Knights detachments from the patched source
  mirror and official transition package.
- Datasheet letters: exact Imperial Knights datasheet rows from the patched
  source mirror, one datasheet or source-coupled kit group per letter.

## Per-Subphase Completion Gate

Each lettered subphase must include:

- normalized source rows and official patch records for the named content;
- catalog records with stable IDs and source IDs;
- explicit unsupported descriptors for unimplemented rule shapes;
- FAQ classification as `advisory_only`, `executable_patch`, or
  `unsupported_executable_change` whenever FAQ rows are in scope;
- deterministic package or catalog hash tests when source data is generated;
- engine behavior tests for any executable rule path;
- replay-safe payload tests for any state-changing rule path;
- a coverage update showing implemented, generic-supported,
  named-handler-required, and unsupported content.

## Deferral Rules

Deferring a detachment or datasheet is allowed only by recording an unsupported
descriptor with a source-linked reason. Deferrals must not create permissive
runtime fallbacks, default datasheet values, hidden text parsing, or alternate
adapter mutation paths.
