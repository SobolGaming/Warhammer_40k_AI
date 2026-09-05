# Astra Militarum: support and roadmap

[All factions](../../FACTION_SUPPORT.md) · [Roadmap](../../FACTION_RULES_REMEDIATION_ROADMAP.md) · [Detailed audit](../audit/astra-militarum.md)

Snapshot: 5 September 2026, 40k.app current view (latest published App-data version 946). Repository baseline: `52673fa1`.

## What can I use?

The current listing contains **70 in-scope datasheet references** and **11 detachment references**. 0 listed units have matching historical component-report rows. Shared source URLs are counted once in the audit, even when several faction views list them.

**Current full-game support is not certified.** Fieldability requires a legal selected roster, current points and equipment, accepted model geometry, and successful engine validation. Playability additionally requires every selected rule to execute; replay verification is a separate gate. A source page or a loaded module does not establish these properties.

Repository matches below are reconciliation candidates. `E` means the baseline report classifies a source row as executable; `Source` means recorded without that classification; `Missing` means no matching row. `E` can coexist with partial or source-only labels in other reports (F-EVID-01). **All require current-source verification.** Exact source-ID reconciliation is F01; matching names do not transfer runtime support.

## Army rules

**Current headings:** Voice of Command.

Officers issue Orders that modify selected units. Order recipients, ranges, duration, and transport exceptions need separate evidence.

[Current army rules](https://www.40k.app/factions/astra-militarum/army-rules)

| Existing army-rule record | Baseline evidence | Current work |
| --- | --- | --- |
| Voice of Command | E; source label: engine_consumed | Compare every current clause; F02 |

## Latest changes to reconcile

- [Version 931 changes](https://www.40k.app/931/factions/astra-militarum/updates): 41 linked changed items before support-scope filtering; use the detailed audit for the in-scope comparison.

## Detachments

DP is a detachment budget, separate from unit/Enhancement points and Stratagem CP. Rule names, force disposition, and complete Enhancement/Stratagem inventories are in the linked audit.

| Detachment | DP / force disposition | Rule headings | Baseline rule | Enh. / Strat. |
| --- | --- | --- | --- | --- |
| [Abhuman Auxiliaries](../audit/astra-militarum.md#detachment-abhuman-auxiliaries) | 1 DP · Take and Hold · Abhuman | Absolutist Principles | Source | 2 / 3 |
| [Armoured Infantry](../audit/astra-militarum.md#detachment-armoured-infantry) | 2 DP · Take and Hold | Keywords; Squadron Command; Order | Source | 4 / 6 |
| [Bridgehead Strike](../audit/astra-militarum.md#detachment-bridgehead-strike) | 1 DP · Priority Assets | Fire Zone Purge | Source | 2 / 3 |
| [Combined Arms](../audit/astra-militarum.md#detachment-combined-arms) | 2 DP · Take and Hold | Born Soldiers | Source | 4 / 6 |
| [Designation Force](../audit/astra-militarum.md#detachment-designation-force) | 1 DP · Reconnaissance · Recon | Designated Targets | Source | 2 / 3 |
| [Grizzled Company](../audit/astra-militarum.md#detachment-grizzled-company) | 3 DP · Priority Assets · Abhuman | Ruthless Discipline | Source | 4 / 6 |
| [Hammer of the Emperor](../audit/astra-militarum.md#detachment-hammer-of-the-emperor) | 2 DP · Purge the Foe | Iron Tread | Source | 4 / 6 |
| [Mechanised Assault](../audit/astra-militarum.md#detachment-mechanised-assault) | 2 DP · Reconnaissance | Armoured Fist | Source | 4 / 6 |
| [Recon Element](../audit/astra-militarum.md#detachment-recon-element) | 2 DP · Reconnaissance · Recon | Masters of Camouflage | Source | 4 / 6 |
| [Siege Regiment](../audit/astra-militarum.md#detachment-siege-regiment) | 2 DP · Disruption | Artillery Support | Source | 4 / 6 |
| [Steel Hammer](../audit/astra-militarum.md#detachment-steel-hammer) | 2 DP · Purge the Foe | Keywords; Ceaseless Cannonade | Source | 4 / 6 |

## Datasheets and points

Costs below retain all displayed model-count tiers, repeat-unit surcharges, and equipment costs. They are an observed reference, not an engine pricing certificate. Open a unit audit for wargear, composition, bases, keywords, Leadership/Support, and abilities.

| Datasheet | Current costs | Repository component evidence |
| --- | --- | --- |
| [Aegis Defence Line](../audit/astra-militarum.md#unit-aegis-defence-line) | 1 model 145 pts | No component row |
| [Armoured Sentinels](../audit/astra-militarum.md#unit-armoured-sentinels) | 1 model 65 pts; 2 models 120 pts | No component row |
| [Artillery Team](../audit/astra-militarum.md#unit-artillery-team) | 1 model 95 pts | No component row |
| [Attilan Rough Riders](../audit/astra-militarum.md#unit-attilan-rough-riders) | 5 models 60 pts; 10 models 120 pts; 3rd+ in your army + 5 pts | No component row |
| [Baneblade](../audit/astra-militarum.md#unit-baneblade) | 1 model 415 pts; 2nd+ in your army + 35 pts | No component row |
| [Banehammer](../audit/astra-militarum.md#unit-banehammer) | 1 model 385 pts; 2nd+ in your army + 35 pts | No component row |
| [Banesword](../audit/astra-militarum.md#unit-banesword) | 1 model 415 pts; 2nd+ in your army + 35 pts | No component row |
| [Basilisk](../audit/astra-militarum.md#unit-basilisk) | 1 model 115 pts; 2nd+ in your army + 20 pts | No component row |
| [Bullgryn Squad](../audit/astra-militarum.md#unit-bullgryn-squad) | 3 models 90 pts; 6 models 200 pts; 2nd+ in your army + 15 pts | No component row |
| [Cadian Castellan](../audit/astra-militarum.md#unit-cadian-castellan) | 1 model 55 pts | No component row |
| [Cadian Command Squad](../audit/astra-militarum.md#unit-cadian-command-squad) | 5 models 60 pts | No component row |
| [Cadian Heavy Weapons Squad](../audit/astra-militarum.md#unit-cadian-heavy-weapons-squad) | 3 models 65 pts | No component row |
| [Cadian Recon Squad](../audit/astra-militarum.md#unit-cadian-recon-squad) | 10 models 80 pts | No component row |
| [Cadian Shock Troops](../audit/astra-militarum.md#unit-cadian-shock-troops) | 10 models 70 pts; 20 models 145 pts | No component row |
| [Catachan Command Squad](../audit/astra-militarum.md#unit-catachan-command-squad) | 5 models 60 pts | No component row |
| [Catachan Heavy Weapons Squad](../audit/astra-militarum.md#unit-catachan-heavy-weapons-squad) | 3 models 70 pts | No component row |
| [Catachan Jungle Fighters](../audit/astra-militarum.md#unit-catachan-jungle-fighters) | 10 models 70 pts; 20 models 135 pts | No component row |
| [Centaur RSV](../audit/astra-militarum.md#unit-centaur-rsv) | 1 model 65 pts; 4th+ in your army + 10 pts | No component row |
| [Chimera](../audit/astra-militarum.md#unit-chimera) | 1 model 75 pts; 4th+ in your army + 10 pts | No component row |
| [Commissar](../audit/astra-militarum.md#unit-commissar) | 1 model 30 pts | No component row |
| [Commissar Graves](../audit/astra-militarum.md#unit-commissar-graves) | 1 model 125 pts | No component row |
| [Commissar Graves on Foot](../audit/astra-militarum.md#unit-commissar-graves-on-foot) | 1 model 65 pts | No component row |
| [Commissar Yarrick](../audit/astra-militarum.md#unit-commissar-yarrick) | 1 model 120 pts | No component row |
| [Death Korps of Krieg](../audit/astra-militarum.md#unit-death-korps-of-krieg) | 10 models 70 pts; 20 models 135 pts | No component row |
| [Death Riders](../audit/astra-militarum.md#unit-death-riders) | 5 models 60 pts; 10 models 110 pts | No component row |
| [Deathstrike](../audit/astra-militarum.md#unit-deathstrike) | 1 model 125 pts; 2nd+ in your army + 10 pts | No component row |
| [Doomhammer](../audit/astra-militarum.md#unit-doomhammer) | 1 model 380 pts; 2nd+ in your army + 30 pts | No component row |
| [Field Ordnance Battery](../audit/astra-militarum.md#unit-field-ordnance-battery) | 2 models 90 pts; Bombast field gun + 10 pts | No component row |
| [Gaunt’s Ghosts](../audit/astra-militarum.md#unit-gaunts-ghosts) | 6 models 95 pts | No component row |
| [Hellhammer](../audit/astra-militarum.md#unit-hellhammer) | 1 model 385 pts; 2nd+ in your army + 30 pts | No component row |
| [Hellhound](../audit/astra-militarum.md#unit-hellhound) | 1 model 125 pts; 3rd+ in your army + 10 pts | No component row |
| [Hippogriff AFV](../audit/astra-militarum.md#unit-hippogriff-afv) | 1 model 70 pts; 2 models 140 pts | No component row |
| [Hydra](../audit/astra-militarum.md#unit-hydra) | 1 model 90 pts | No component row |
| [Kasrkin](../audit/astra-militarum.md#unit-kasrkin) | 10 models 105 pts; 3rd+ in your army + 15 pts | No component row |
| [Krieg Combat Engineers](../audit/astra-militarum.md#unit-krieg-combat-engineers) | 5 models 65 pts; 10 models 95 pts; 3rd+ in your army + 10 pts | No component row |
| [Krieg Command Squad](../audit/astra-militarum.md#unit-krieg-command-squad) | 6 models 60 pts | No component row |
| [Krieg Heavy Weapons Squad](../audit/astra-militarum.md#unit-krieg-heavy-weapons-squad) | 4 models 70 pts; Krieg heavy flamer + 5 pts | No component row |
| [Leman Russ Battle Tank](../audit/astra-militarum.md#unit-leman-russ-battle-tank) | 1 model 160 pts; 3rd+ in your army + 15 pts; Lascannon + 5 pts; Multi-melta + 5 pts; Plasma cannon + 5 pts | No component row |
| [Leman Russ Commander](../audit/astra-militarum.md#unit-leman-russ-commander) | 1 model 195 pts; 3rd+ in your army + 15 pts; Demolisher battle cannon + 15 pts; Lascannon + 5 pts; Multi-melta + 5 pts; Plasma cannon + 5 pts | No component row |
| [Leman Russ Demolisher](../audit/astra-militarum.md#unit-leman-russ-demolisher) | 1 model 160 pts; 3rd+ in your army + 15 pts; Lascannon + 5 pts; Multi-melta + 5 pts; Plasma cannon + 5 pts | No component row |
| [Leman Russ Eradicator](../audit/astra-militarum.md#unit-leman-russ-eradicator) | 1 model 145 pts; 3rd+ in your army + 15 pts; Lascannon + 5 pts; Multi-melta + 5 pts; Plasma cannon + 5 pts | No component row |
| [Leman Russ Executioner](../audit/astra-militarum.md#unit-leman-russ-executioner) | 1 model 145 pts; 3rd+ in your army + 15 pts; Lascannon + 5 pts; Multi-melta + 5 pts; Plasma cannon + 5 pts | No component row |
| [Leman Russ Exterminator](../audit/astra-militarum.md#unit-leman-russ-exterminator) | 1 model 160 pts; 3rd+ in your army + 15 pts; Lascannon + 5 pts; Multi-melta + 5 pts; Plasma cannon + 5 pts | No component row |
| [Leman Russ Punisher](../audit/astra-militarum.md#unit-leman-russ-punisher) | 1 model 130 pts; 3rd+ in your army + 15 pts; Lascannon + 5 pts; Multi-melta + 5 pts; Plasma cannon + 5 pts | No component row |
| [Leman Russ Vanquisher](../audit/astra-militarum.md#unit-leman-russ-vanquisher) | 1 model 130 pts; 3rd+ in your army + 15 pts; Lascannon + 5 pts; Multi-melta + 5 pts; Plasma cannon + 5 pts | No component row |
| [Lord Marshal Dreir](../audit/astra-militarum.md#unit-lord-marshal-dreir) | 1 model 75 pts | No component row |
| [Lord Solar Leontus](../audit/astra-militarum.md#unit-lord-solar-leontus) | 1 model 130 pts | No component row |
| [Manticore](../audit/astra-militarum.md#unit-manticore) | 1 model 150 pts; 2nd+ in your army + 20 pts | No component row |
| [Militarum Tempestus Command Squad](../audit/astra-militarum.md#unit-militarum-tempestus-command-squad) | 5 models 85 pts; 3rd+ in your army + 10 pts | No component row |
| [Ministorum Priest](../audit/astra-militarum.md#unit-ministorum-priest) | 1 model 35 pts | No component row |
| [Nork Deddog](../audit/astra-militarum.md#unit-nork-deddog) | 1 model 60 pts | No component row |
| [Ogryn Bodyguard](../audit/astra-militarum.md#unit-ogryn-bodyguard) | 1 model 40 pts | No component row |
| [Ogryn Squad](../audit/astra-militarum.md#unit-ogryn-squad) | 3 models 60 pts; 6 models 120 pts | No component row |
| [Primaris Psyker](../audit/astra-militarum.md#unit-primaris-psyker) | 1 model 60 pts | No component row |
| [Ratlings](../audit/astra-militarum.md#unit-ratlings) | 5 models 60 pts; 10 models 100 pts | No component row |
| [Rogal Dorn Battle Tank](../audit/astra-militarum.md#unit-rogal-dorn-battle-tank) | 1 model 260 pts; 2nd+ in your army + 15 pts | No component row |
| [Rogal Dorn Commander](../audit/astra-militarum.md#unit-rogal-dorn-commander) | 1 model 290 pts; 2nd+ in your army + 15 pts | No component row |
| [Scout Sentinels](../audit/astra-militarum.md#unit-scout-sentinels) | 1 model 55 pts; 2 models 100 pts | No component row |
| [Shadowsword](../audit/astra-militarum.md#unit-shadowsword) | 1 model 375 pts; 2nd+ in your army + 30 pts | No component row |
| [Sly Marbo](../audit/astra-militarum.md#unit-sly-marbo) | 1 model 55 pts | No component row |
| [Stormlord](../audit/astra-militarum.md#unit-stormlord) | 1 model 395 pts; 2nd+ in your army + 35 pts | No component row |
| [Stormsword](../audit/astra-militarum.md#unit-stormsword) | 1 model 430 pts; 2nd+ in your army + 35 pts | No component row |
| [Taurox](../audit/astra-militarum.md#unit-taurox) | 1 model 65 pts; 4th+ in your army + 10 pts | No component row |
| [Taurox Prime](../audit/astra-militarum.md#unit-taurox-prime) | 1 model 75 pts; 4th+ in your army + 10 pts | No component row |
| [Tech-Priest Enginseer](../audit/astra-militarum.md#unit-tech-priest-enginseer) | 1 model 45 pts | No component row |
| [Tempestus Aquilons](../audit/astra-militarum.md#unit-tempestus-aquilons) | 10 models 95 pts | No component row |
| [Tempestus Scions](../audit/astra-militarum.md#unit-tempestus-scions) | 5 models 75 pts; 10 models 150 pts; 3rd+ in your army + 10 pts | No component row |
| [Ursula Creed](../audit/astra-militarum.md#unit-ursula-creed) | 1 model 85 pts | No component row |
| [Valkyrie](../audit/astra-militarum.md#unit-valkyrie) | 1 model 170 pts; 3rd+ in your army + 10 pts | No component row |
| [Wyvern](../audit/astra-militarum.md#unit-wyvern) | 1 model 95 pts; 2nd+ in your army + 20 pts | No component row |

## Work remaining

1. **F00–F01:** retain approved source evidence, resolve scope and source IDs, and reconcile all updates since the July baseline.
2. **F02–F03:** certify army rules and implement the listed missing detachment rules, Enhancements, Upgrades, and Stratagems through generic services where possible.
3. **F04–F07:** reconcile every unit’s costs, composition, profiles, equipment options, geometry, keywords, attachments, and Core/Unit abilities. Each linked unit audit is an explicit open checklist.
4. **F08–F09:** exercise legal and invalid rosters through the shared adapter decision path, viewer projections, restore, replay, and full-game scenarios.

## Evidence

- [Detailed current-source inventory](../audit/astra-militarum.md)
- [Source observation register](../../FACTION_AUDIT_SOURCES.md)
- [Generated historical evidence](../astra-militarum.md)
- [Status definitions and acceptance checklist](../../FACTION_RULES_REMEDIATION_ROADMAP.md#status-and-acceptance-gates)
