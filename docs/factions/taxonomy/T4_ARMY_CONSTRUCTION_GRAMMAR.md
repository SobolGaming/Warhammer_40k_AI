# T4 — Army-construction grammar

[Taxonomy index](README.md) · [Faction roadmap](../../FACTION_RULES_REMEDIATION_ROADMAP.md) · [Core P25A–C](../../CORE_RULES_REMEDIATION_ROADMAP.md) · [S2 identity model](../identity/S2_IDENTITY_MODEL.md) · [Track U classification](../updates/U_CLASSIFICATION_SYSTEM.md) · [Observation register](../../FACTION_AUDIT_SOURCES.md)

This survey is Track T item T4. It is planning evidence delivered read-only to
Core orders P25A, P25B and P25C. It does not implement engine semantics, populate
faction records, or admit content. FM0 regenerates construction facts from the
retained content set and reconciles them with this document.

Machine-readable family catalog: [`t4_constraint_families.json`](t4_constraint_families.json).

## 1. Purpose and delivery contract

T4 closes the army-construction grammar that Core P25C must expose as typed,
source-neutral constraint surfaces before any faction implementation wave.

**P25C implements empty schema and Core-owned evaluators only.** It must not
populate or evaluate faction-specific records. Existing content branches in
`engine/army_mustering.py` (Shadow Legion, Corsair Coterie, Be'lakor-by-name)
remain debt item 1 in FM0; they migrate onto these surfaces later.

Split of Core owners:

| Owner | Grammar this survey delivers |
| --- | --- |
| P25A (C25-01, C25-02) | Battle-size points, DP budget, Enhancement limit, unit limit, Battleline and Dedicated Transport doubling, Epic Hero limit, Incursion single 3-DP exception, Upgrade copy accounting |
| P25B (C25-03) | Model-specific Warlord, model-specific Enhancement bearer, Upgrade eligibility for non-CHARACTER units, cannot-be-WARLORD over must-be-WARLORD |
| P25C (C25-04) | Duplicate-detachment prohibition; typed required/prohibited unit and required/prohibited other-detachment records; Support-must-attach certification; force-disposition consistency |

Related-army pacts, detachment Keywords grants, extra listing tags, and
Enhancement-only inventories are surveyed here so P25C does not invent a
faction-shaped schema. Their records are populated in FM0.

## 2. Methodology and snapshot

| Item | Value |
| --- | --- |
| Corpus snapshot | 5 September 2026, 40k.app current views, App-data 946 |
| Directory fingerprint | [factions](https://www.40k.app/factions) `8b9c6ab5fe8e80d4082ef2ddb800a15453e719fe89da36b507e2b1a8124c0a11` at 2026-09-05T20:36:45.654Z |
| Feed fingerprint | [updates](https://www.40k.app/factions/updates) `9ffcc106cd467b418a3ac862efbd05c8ab64c730e6601f0fa3ba331b2f2c5202` at 2026-09-05T20:36:35.214Z |
| Structural inventory | All 40 admitted guides under `docs/factions/guides/` (506 detachment listing rows) |
| Operative samples | Live 40k.app pages fetched for Core 25, selected army rules, and selected Keywords/Restrictions detachments during this survey |
| Core 25 locators | [25.00 Muster Armies](https://www.40k.app/rules/25-muster-armies), including 25.03 Select Battle Size and 25.04 Fill Your Army Roster |
| Engine inspection | Read-only: `DetachmentDefinition`, `BattleSizeMusteringPolicy`, `validate_detachment_selection`, `army_mustering.py` |

Counts below are listing observations, including inherited Space Marine chapter
and related-army views. They are not distinct-rule denominators. S2 records
identity; the September register expects about 270–300 distinct detachments
after resolution. This survey's unique listing names: **270**. The closed
identity axes are in
[S2_IDENTITY_MODEL.md](../identity/S2_IDENTITY_MODEL.md).

This document does not copy bulk operative text. Sampled clauses are paraphrased
and linked. Exact transcription remains an F00/S3a obligation.

## 3. Core 25 grammar (P25A / P25B / P25C)

Authoritative current App wording is the 40k.app Core 25 page. P25A already
records the Incursion table that the engine does not yet enforce.

### 3.1 Battle-size budgets (P25A)

Observed current 25.03 table (Incursion and Strike Force). Battleline and
Dedicated Transport each use **double** the ordinary unit limit. Epic Hero
units are limited to **1**.

| Battle size | Points | DP | Enhancement limit | Ordinary unit limit | Battleline / Dedicated Transport |
| --- | ---: | ---: | ---: | ---: | ---: |
| Incursion | 1000 | 2 | 2 | 2 | 4 |
| Strike Force | 2000 | 3 | 4 | 3 | 6 |

Incursion footnote: a player may select a **single** 3-DP detachment as the
army's only detachment. That is not a general 3-DP allowance at Incursion.

**Onslaught hold (T4-HOLD-ONSLAUGHT).** The current 25.03 table does not list
Onslaught. Faction army rules and detachment admission clauses observed in this
survey name Onslaught with points or count caps (Daemonic Pact 750 pts, Cults of
the Dark Gods 750 pts, Corsairs 750 pts, Shadow Legion Thralls 1500 pts, Khorne
Daemonkin / Tallyband Summoners 1500 pts, Cult Ambush 14 Resurgence points).
The engine currently ships an Onslaught policy of 3000 points, 4 DP, 4
Enhancements, ordinary limit 3, Battleline limit 6. P25A must treat Onslaught
as unresolved against the Core table unless another Core locator is retained.
Faction pacts must not invent a Core Onslaught row.

Current engine `BattleSizeMusteringPolicy.incursion()` still uses Enhancement
limit 4 and ordinary unit limit 3 with Battleline 6 and no independent
Dedicated Transport doubling. That is C25-01/C25-02, owned by P25A.

### 3.2 Multiple detachments and DP (P25A + P25C)

An army may select more than one detachment. Combined detachment DP cannot
exceed the battle-size DP limit, except the Incursion single 3-DP footnote.
Enhancements and Stratagems available to the army are the union of the selected
detachments' inventories, then counted against the battle-size Enhancement
limit (P25A) and Core Stratagem timing rules (not T4).

### 3.3 Duplicate-detachment prohibition (P25C)

25.04 forbids selecting the same detachment more than once. `DetachmentSelection`
already rejects duplicate detachment IDs in the request tuple. P25C must certify
that prohibition against Core 25.04 as a roster rule, not only as identifier
uniqueness, so S2 identity resolution cannot admit the same source detachment
under two catalog IDs.

### 3.4 Force-disposition consistency (P25C)

Core Force Dispositions observed on listings: Take and Hold, Purge the Foe,
Priority Assets, Reconnaissance, Disruption.

`ArmyMusterRequest` carries one `force_disposition_id`. That is the correct
army-level selection.

Current `selected_force_disposition_ids` builds the **union** of every selected
detachment's `force_disposition_ids`. T4 reads Core consistency as: the army's
chosen Core Force Disposition must be provided by **every** selected
detachment (**intersection**), not merely by one of them. P25C should certify
intersection unless retained 25.04 wording says otherwise.

One listing, Orks [War Horde](https://www.40k.app/factions/orks/detachments/war-horde),
displays two Core Force Dispositions on a single 3-DP detachment
(`Take and Hold / Purge the Foe`). The army still selects one Core Force
Disposition; that detachment offers either.

Listing pages also display extra tokens after the Core Force Disposition
(Acrobatic, Mutant, Auxiliary, and others; full set in §5.3). Those tokens are
**not** Core Force Dispositions. They must not be stored on
`force_disposition_ids`. They are content listing tags for FM0 / S2.

### 3.5 Required and prohibited units and other detachments (P25C)

25.04 states that Detachment rules may require or forbid units and may require
or forbid other detachments. `DetachmentDefinition` today has
`unit_datasheet_ids` (treated as grants) and no constraint records. That is
C25-04.

P25C must add typed, source-neutral records:

| Family ID | Meaning |
| --- | --- |
| `required_unit` | Roster must include at least one unit matching the `UnitSelector` |
| `prohibited_unit` | Roster must not include a unit matching the `UnitSelector` |
| `required_other_detachment` | Roster must also include another detachment matching the `DetachmentSelector` |
| `prohibited_other_detachment` | Roster must not include another detachment matching the `DetachmentSelector` |

Unit and other-detachment families do not share one selector type. A
`UnitSelector` cannot name a detachment, and a `DetachmentSelector` cannot
name a datasheet. Both are source-ID-linked and must not gate on display
names. `UnitSelector` atoms demanded by this corpus: datasheet identity,
keyword all/any, keyword exclusion, characteristic thresholds (example:
Wounds 14+), and Epic Hero / CHARACTER / Battleline membership.
`DetachmentSelector` atoms: one canonical project-owned detachment ID, or a
closed set of such IDs, with an optional exclude wrapper. "Another"
detachment is any selected detachment other than the constraint owner.
Runtime must not parse rule text. No faction rows are required to ship these
empty selector types.

Sampled Keywords headings are often **keyword grants**, not must/cannot
include (see §6). Sampled Restrictions headings are often **related-army
admission with caps**, not "cannot include Detachment X". No complete
required-other-detachment or prohibited-other-detachment example was retained
in this survey's live fetches (T4-HOLD-OTHER-DETACHMENT-EXAMPLE). P25C still
ships the empty typed slots because Core 25.04 names them.

`validate_detachment_selection` currently rejects a detachment whose
`unit_datasheet_ids` is empty as "awaiting source". That assumption does not
match Core 25: most detachments admit the army faction's legal datasheets and
then apply constraints. P25C must not treat an empty grant list as missing
source once constraint records exist.

### 3.6 Enhancement and Upgrade accounting (P25A) and bearer (P25B)

25.04 grammar, paraphrased:

- CHARACTER only unless the record is an Upgrade.
- No Epic Hero bearer.
- Unique Enhancements: one copy.
- Upgrades: up to three copies; the second and third copies do not count toward
  the battle-size Enhancement limit and still pay points.
- One Enhancement or Upgrade per unit, including the attached rules unit.
- Bearer selection is a specific eligible model, not a unit ID with WARLORD
  sprayed onto every model (P25B; C25-03).

Engine `EnhancementDefinition` already has `subtypes` including Upgrade and
keyword target filters. It does not persist a specific bearer model. P25B owns
that identity.

Corsair Coterie currently raises the effective Enhancement limit in
`army_mustering.py`. That is a content branch (debt item 1), not Core 25. FM0
must express it as a source-linked exception record on the P25A count surface,
not as a named Python gate.

### 3.7 Warlord (P25B)

25.04 grammar, paraphrased:

1. Select a CHARACTER unit that has the army Faction keyword.
2. Select one CHARACTER model in that unit as WARLORD.
3. Datasheet or ability text may mark a model as must-be-WARLORD or
   cannot-be-WARLORD; **cannot** wins.

Allied and related-army models observed in this survey are typically forbidden
as WARLORD (Daemonic Pact, Corsairs, Freeblades, Dreadblades, Khorne Daemonkin
Blood Legions models, Tallyband Summoners Plague Legions models). Those are
content records on the same precedence rule, populated in FM0.

### 3.8 Support must attach (P25C)

Every Support unit must be attached to an eligible Bodyguard. The engine already
validates required Support attachment. P25C certifies that existing path against
25.04; it does not invent a second attachment owner.

## 4. Corpus structure (planning counts)

Parsed from the 40 guides' detachment tables at the snapshot in §2.

| Measure | Count |
| --- | ---: |
| Admitted views | 40 |
| Detachment listing rows (view, name) | 506 |
| Unique listing names | 270 |
| DP 1 listings | 156 |
| DP 2 listings | 254 |
| DP 3 listings | 96 |
| Listings with a Keywords heading | 50 (21 unique names) |
| Listings with a Restrictions heading | 25 (25 unique names) |
| Combined Keywords or Restrictions unique names | 44 |
| Listings with both Keywords and Restrictions | The Lost Brethren; Company of Hunters |
| Enhancement-zero listings | 0 |
| Stratagem-zero listings | 16 (5 unique names) |
| Listings with two Core Force Dispositions | 1 (War Horde) |

The combined Keywords/Restrictions unique-name count is 21 + 25 − 2: The Lost
Brethren and Company of Hunters appear in both heading lists and are not
counted twice.

Enhancement-only (Stratagem inventory 0), unique names:

| Detachment | Enh. / Strat. | DP | Core Force Disposition | Views in this inventory |
| --- | ---: | ---: | --- | --- |
| Brute Bosses | 6 / 0 | 1 | Purge the Foe | Orks |
| Wurrband | 3 / 0 | 1 | Disruption | Orks |
| Librarius Conclave | 5 / 0 | 1 | Reconnaissance | Space Marines and inherited chapter views (12 listings) |
| Sanctified Orators | 1 / 0 | 1 | Disruption | Adepta Sororitas |
| The Living Miracle | 1 / 0 | 1 | Disruption | Black Templars |

An empty Stratagem inventory is legal Core construction. P25C must not treat
`stratagem_ids == ()` as missing source. Detachment-offered Enhancement count
is not the battle-size Enhancement limit.

Typical inventories (not Core rules): 1-DP often 2 Enhancements / 3 Stratagems;
2-DP and 3-DP often 4 / 6. Counterexamples exist (Veiled Blade Elimination
Force is 1 DP with 4 / 6; Madcap Meks is 1 DP with 3 / 1; Enhancement-only
rows above). Do not encode those frequencies as Core limits.

## 5. Extra listing tags versus Core Force Disposition

### 5.1 Core Force Dispositions

Take and Hold, Purge the Foe, Priority Assets, Reconnaissance, Disruption.

### 5.2 Dual Core Force Disposition

Orks War Horde: 3 DP, Take and Hold / Purge the Foe. Store two Core IDs on that
detachment record. The army still selects one.

### 5.3 Extra tags (not Core Force Dispositions)

| Tag | Unique listing names |
| --- | --- |
| Acrobatic | Fateful Performance, Ghosts of the Webway, Serpent's Brood, Twilight Flickers |
| Mutant | Servants of Change, Warpmeld Pact |
| Doomed | Rage-cursed Onslaught, The Lost Brethren, Wrath of the Doomed |
| Reverend | Champions of Faith, Sacred Champions |
| Lions | Lions of the Emperor, Tharanatoi Hammerblow |
| Armoury | Might of the Moritoi, Solar Spearhead |
| Data-psalm | Data-psalm Conclave, Luminen Auto-Choir |
| Abhuman | Abhuman Auxiliaries, Grizzled Company |
| Recon | Designation Force, Recon Element |
| Grace | Angelic Inheritors, Legacy of Grace |
| Nightmare | Murdertalon Raiders, Nightmare Hunt |
| Covens | Covenite Coterie, Tools of Torment |
| Wych Cult | Exhibition of Slaughter, Spectacle of Spite |
| Kabal | Kabalite Agonysts, Kabalite Cartel |
| Purestrain | Biosanctic Broodsurge, Purestrain Broodswarm |
| Hosts | Host of Ascension, Xenocult Masses |
| Armigers | Spearhead-at-Arms, Throne-bonded Outriders |
| Hearthband | Hearthband, Hearthguard Covenant |
| Dynasty | Awakened Dynasty, Hand of the Dynasty |
| Hypercrypt | Hypercrypt Legion, The Phaeron's Armoury |
| Auxiliary | Auxiliary Cadre, Kroot Hunting Pack |
| Battlesuit | Experimental Prototype Cadre, Retaliation Cadre |

FM0 may record these as listing tags or keyword-like eligibility tokens. P25C
must not add them to the Core Force Disposition enum.

## 6. Keywords versus Restrictions (must/cannot shapes)

A heading named Keywords is not automatically a construction constraint. Live
samples:

| Detachment | Heading | Construction shape |
| --- | --- | --- |
| [Shadow Legion](https://www.40k.app/factions/chaos-daemons/detachments/shadow-legion) | Thralls of the First Prince; Keywords | **Prohibited units** (Daemon Prince and Epic Hero, excluding Be'lakor); **related-army allow-list** of named Heretic Astartes units with Incursion/Strike Force/Onslaught points caps 500/1000/1500; **keyword grants** (SHADOW LEGION, UNDIVIDED, Deep Strike for some) |
| [Cult of Blood](https://www.40k.app/factions/world-eaters/detachments/cult-of-blood) | Keywords | **Keyword grant only**: JAKHALS and GOREMONGERS gain BATTLELINE |
| [Armoured Speartip](https://www.40k.app/factions/space-marines/detachments/armoured-speartip) | Keywords | **Keyword grant only**: ADEPTUS ASTARTES TRANSPORT (excluding FLY) with Wounds 14+ gain HEAVY TRANSPORT |
| [Khorne Daemonkin](https://www.40k.app/factions/blood-legions/detachments/khorne-daemonkin) | Restrictions | **Related-army admission**: BLOOD LEGIONS units at 500/1000/1500 pts; those models cannot be WARLORD |
| [Tallyband Summoners](https://www.40k.app/factions/plague-legions/detachments/tallyband-summoners) | Plague Legions | Same shape for PLAGUE LEGIONS into a Death Guard army; those models cannot be WARLORD |

Keyword grants belong to the Track G keyword family and to mustering effective
keywords. They are not `required_unit` / `prohibited_unit` unless the grant
changes Battleline counting or other construction limits (Cult of Blood does:
gaining BATTLELINE changes P25A duplicate limits). P25C evaluators must consume
effective keywords after grants.

Unique listing names with a Keywords heading: Armoured Infantry, Armoured
Speartip, Champions of Faith, Chaos Cult, Company of Hunters, Cult of Blood,
Dêlve Assault Shift, Headhunter Task Force, Houndpack Lance, Kroot Hunting
Pack, Null Maiden Vigil, Shadow Legion, Shamblerot Vectorium, Solar Spearhead,
Spearhead-at-Arms, Spirit Conclave, Steel Hammer, Subterranean Assault, The
Lost Brethren, Warpmeld Pact, Windrider Host.

Unique listing names with a Restrictions heading: Angelic Inheritors, Black
Spear Task Force, Blade of Ultramar, Changehost of Deceit, Companions of
Vehemence, Company of Hunters, Emperor's Shield, Forgefather's Seekers,
Godhammer Assault Force, Hammer of Avernii, Inner Circle Task Force, Khorne
Daemonkin, Liberator Assault Group, Lion's Blade Task Force, Pactbound Zealots,
Pantheon of Woe, Rage-cursed Onslaught, Reclamation Force, Saga of the Great
Wolf, Shadowmark Talon, Spearpoint Task Force, The Angelic Host, The Lost
Brethren, Unforgiven Task Force, Vindication Task Force.

FM0 extracts every Keywords/Restrictions body from retained pages onto the
families in §8. This survey does not claim those 44 unique names are fully
transcribed.

## 7. Related-army admission and caps

Related-army rules are not Core 25 tables. They consume battle size, Warlord
precedence, Enhancement prohibition, and (once P25C exists) selector records.

Two layers appear in this corpus:

1. **Army-faction admission gate.** Related daemon views cannot be selected as
   Army Faction unless a rule says otherwise. Observed complete text: Pact of
   Blood and Pact of Sorcery (`When mustering your army, unless specifically
   stated otherwise, you cannot select {RELATED FACTION} as your Army Faction`).
   Engine `FORBIDDEN_DEFAULT_ARMY_FACTION_RULE_BY_KEYWORD` already maps Blood
   Legions, Legions of Excess, Plague Legions, and Scintillating Legions. Pact
   of Decay / Pact of Excess bodies were truncated or bot-blocked in later
   fetches (T4-HOLD-PACT-BODIES); treat them as the same gate family until
   retained text says otherwise.
2. **Host-army or detachment admission.** A host army or a specific detachment
   may include the related units under points or count caps. Those clauses are
   the "specifically stated otherwise" that makes the related units legal
   without selecting the related view as Army Faction.

S2 records ownership: Khorne Daemonkin is listed on the Blood Legions view
and admits BLOOD LEGIONS units into a World Eaters army. Tallyband Summoners is
listed on the Plague Legions view and admits PLAGUE LEGIONS units into a Death
Guard army. Parallel listings Changehost of Deceit (Scintillating) and Carnival
of Excess (Legions of Excess) match that pattern from headings; their full
bodies are T4-HOLD-DAEMONKIN-PARALLELS.

### 7.1 Related-army inventory

| Rule | Where it lives | Construction shape | Live text this survey | Engine today |
| --- | --- | --- | --- | --- |
| Daemonic Pact | Chaos Daemons army rules | If every model is CHAOS KNIGHTS or HERETIC ASTARTES, include LEGIONES DAEMONICA; 250/500/750 pts; no allied WARLORD or Enhancements; per-god non-Battleline cannot exceed Battleline of that god | Complete | Named Python in `army_mustering.py` |
| Cults of the Dark Gods | Chaos Space Marines army rules | Include named cult datasheets; replace Faction keywords with HERETIC ASTARTES; 250/500/750 pts | Complete | Named Python |
| Corsairs and Travelling Players | Drukhari army rules | Include HARLEQUINS and ANHRATHE; 250/500/750 pts; no allied WARLORD or Enhancements | Complete | Named Python |
| Freeblades | Imperial Knights army rules | If every model is IMPERIUM: one TITANIC IMPERIAL KNIGHTS **or** up to three ARMIGER; no allied WARLORD or Enhancements | Complete | Named Python |
| Dreadblades | Chaos Knights army rules | Chaos host: one TITANIC **or** up to three WAR DOG; no allied WARLORD or Enhancements | Bot-blocked this session; matrix and tests describe the same XOR count | Named Python |
| Space Marine Chapters | Space Marines army rules | One Chapter; extra Black Templars, Space Wolves, Deathwatch prohibitions; Deathwatch Agents exception names out-of-scope Legends content (do not ingest) | Complete | Named Python |
| Disparate Paths | Aeldari / Harlequins / Ynnari army-rule heading | Datasheet-carried faction access into an ASURYANI Battle Focus army; not a 250/500/750 pts pact in the engine consumer | Bot-blocked; engine `DatasheetFactionAccessBinding` | Generic-ish binding, still Aeldari-owned |
| Assigned Agents | Imperial Agents army rules | IMPERIUM host that is not Agents may include Agents by battle-size category caps; Onslaught named on the page | First fetch then bot-blocked (T4-HOLD-ASSIGNED-AGENTS) | None |
| Pact of Blood / Decay / Excess / Sorcery | Related daemon views (and some host views) | Army-faction gate; host inclusion is on daemonkin-style detachments | Blood and Sorcery gates complete; Decay/Excess bodies held | Gate only |
| Shadow Legion Thralls | Shadow Legion detachment | Allow-list + 500/1000/1500 pts + prohibitions + keyword grants | Complete | Named Python |
| Khorne Daemonkin Restrictions | Blood Legions listing | BLOOD LEGIONS 500/1000/1500 pts; cannot be WARLORD | Complete | None |
| Tallyband Summoners Plague Legions | Plague Legions listing | PLAGUE LEGIONS 500/1000/1500 pts; cannot be WARLORD | Complete | None |
| Brood Brothers | Brood Brothers Auxilia detachment heading, not GSC army rules | Detachment-level related Astra Militarum admission (operative body not fetched) | Heading only | None |
| Bondsman, Da Boss, Super-heavy Walker | Various army rules | Not army-construction admission | Complete where fetched | N/A |

Daemonic Pact, Cults of the Dark Gods, and Corsairs all name Onslaught. That
reinforces T4-HOLD-ONSLAUGHT: P25A must decide the Core battle-size row;
content pacts may still key caps by an Onslaught token if Core later admits it
or if the pact is evaluated only when the declared battle size is Onslaught.

Freeblades / Dreadblades use a **count XOR**, not a points cap: one TITANIC or
up to three Armiger / War Dog models. That is a distinct family from 250/500/750
points pacts.

Assigned Agents is a **category count cap** (Retinue / Character / Requisitioned
style), not a single points pool. Empty Dedicated Transport destruction at
Declare Battle Formations is Core 18.01 / P18A, not an Agents-only rule.

Space Marine Chapters current text names a Legends Agents exception for Kill
Team Cassius. CORE V2 must not ingest, scaffold, or expose that datasheet.
Record the clause as out-of-scope exception text on an in-scope army rule (S2:
no catalog row / F-SCOPE).

### 7.2 Related-army construction families

| Family ID | Typical parameters |
| --- | --- |
| `army_faction_admission_gate` | Forbidden army Faction keyword unless a source-linked exception record is present |
| `related_army_points_cap` | Included selector; points cap by battle size; host keyword predicate |
| `related_army_count_xor` | One selector-A **or** up to N of selector-B |
| `related_army_category_count_cap` | Per-category maxima by battle size |
| `allied_warlord_prohibition` | Selector cannot be WARLORD |
| `allied_enhancement_prohibition` | Selector cannot receive Enhancements |
| `faction_keyword_replacement` | Replace Faction keywords on admitted units |
| `god_battleline_pairing` | Per-keyword non-Battleline ≤ Battleline |
| `datasheet_faction_access` | Datasheet-carried permission into a host army |

These families are FM0 content records. The JSON catalog assigns them to FM0,
not to P25C. That assignment is the owner: P25C must not add extra related-army
kinds, empty or otherwise, to the Core constraint schema. When FM0 later
populates them, they reuse the P25C `UnitSelector` (and `DetachmentSelector`
if a pact names another detachment) rather than inventing a parallel selector
language. P25C still must not branch on faction IDs.

## 8. Typed P25C constraint catalog

Minimum P25C schema (empty at merge):

```text
DetachmentDefinition
  + construction_constraints: tuple[ConstructionConstraint, ...]

ConstructionConstraint
  constraint_id: stable project ID
  source_id: retained source ID
  kind: required_unit | prohibited_unit
        unit_selector: UnitSelector
  kind: required_other_detachment | prohibited_other_detachment
        detachment_selector: DetachmentSelector
```

`UnitSelector` is a closed typed union: datasheet IDs, keyword all/any/none,
characteristic predicates, Epic Hero / Battleline / CHARACTER flags, and an
exclude wrapper. `DetachmentSelector` is a separate closed typed union:
one canonical project-owned detachment ID, a closed set of such IDs, and an
optional exclude wrapper. A unit family must carry a `UnitSelector`; an
other-detachment family must carry a `DetachmentSelector`. Neither union
includes the other domain. No display-name or locally re-normalized token
gates. Shipping the empty selector types does not populate faction rows.

Core-owned evaluators in the same P25C PR:

1. Duplicate-detachment prohibition.
2. Support-must-attach certification of the existing path.
3. Force-disposition intersection against the army's single selected Core
   Force Disposition.
4. Fail-closed application of any constraint records that happen to be present
   on `DetachmentDefinition` (none at P25C merge).

Do **not** in P25C:

- Populate Shadow Legion, Corsair, Chapter, or pact rows.
- Add the §7.2 related-army families to the Core constraint schema; those
  remain FM0.
- Treat extra listing tags as Force Dispositions.
- Invent an Onslaught Core table row.
- Keep "empty `unit_datasheet_ids` means awaiting source" once the grant/constraint
  model is in place.
- Reject Enhancement-only detachments for empty Stratagem lists.

P25A/P25B remain responsible for budgets, Upgrade arithmetic, and model-level
Warlord/bearer identity. T3 still owns in-game bearer/target grammar; T4 only
owns mustering-time bearer and Warlord selection.

## 9. Engine gaps this survey is not fixing

Read-only findings for later Core or FM0 work:

| Gap | Current behavior | Owner |
| --- | --- | --- |
| Incursion Enhancement and unit limits | Policy still 4 Enhancements and ordinary limit 3 | P25A |
| Dedicated Transport doubling | Not an independent limit | P25A |
| Onslaught Core row | Engine has 3000/4 DP/4 Enhancements; Core 25.03 table omits Onslaught | P25A |
| Warlord/bearer model identity | Unit-level IDs | P25B |
| Required/prohibited constraint records | Missing on `DetachmentDefinition` | P25C |
| Force-disposition union vs intersection | Union | P25C |
| Empty unit grants rejected | Treated as awaiting source | P25C |
| Content-specific mustering branches | Shadow Legion, Corsair Coterie, Be'lakor name, Chapter lists, pacts | FM0 debt item 1 |
| Assigned Agents, daemonkin detachments, Brood Brothers | No generic records | FM0 after P25C |

## 10. Open holds

| ID | Hold | Unblocks |
| --- | --- | --- |
| T4-HOLD-ONSLAUGHT | Core 25.03 table vs faction Onslaught caps | P25A |
| T4-HOLD-ASSIGNED-AGENTS | Assigned Agents operative body not re-retained after bot challenge | S3a, then FM0 records |
| T4-HOLD-DISPARATE-PATHS | Aeldari army-rules page bot-blocked | S3a |
| T4-HOLD-PACT-BODIES | Pact of Decay / Pact of Excess complete sentences | S3a |
| T4-HOLD-DAEMONKIN-PARALLELS | Changehost of Deceit, Carnival of Excess full Restrictions/admission text | S3a |
| T4-HOLD-BROOD-BROTHERS | Brood Brothers Auxilia operative admission text | S3a |
| T4-HOLD-OTHER-DETACHMENT-EXAMPLE | No retained required/prohibited-other-detachment example | P25C still ships empty slots; FM0 fills or records absence |
| F-SCOPE-01 | Warbuggies identity; listed unresolved in S2 with no catalog_id | Later source review |
| Legends exception on Space Marine Chapters | Kill Team Cassius named as Legends | S2: no catalog row; do not ingest |

## 11. What "T4 delivered to P25C" means

P25C may start. It has:

- the Core 25.04 constraint families and the separate `UnitSelector` /
  `DetachmentSelector` types those families need;
- the Core-owned evaluators it must certify without faction rows;
- the split against P25A/P25B;
- the related-army family list as FM0 demand, so P25C keeps `UnitSelector`
  reusable without adding those kinds now;
- the War Horde dual Core Force Disposition and extra-tag warning;
- the Enhancement-only legality warning;
- the Onslaught hold so it does not invent a Core battle-size row.

FM0, not P25C, regenerates this survey from retained pages and attaches real
constraint rows to the empty surfaces.
