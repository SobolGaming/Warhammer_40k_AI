# T’au Empire: support and roadmap

[All factions](../../FACTION_SUPPORT.md) · [Roadmap](../../FACTION_RULES_REMEDIATION_ROADMAP.md) · [Detailed audit](../audit/tau-empire.md)

Snapshot: 5 September 2026, 40k.app current view (latest published App-data version 946). Repository baseline: `52673fa1`.

## What can I use?

The current listing contains **40 in-scope datasheet references** and **7 detachment references**. 0 listed units have matching historical component-report rows. Shared source URLs are counted once in the audit, even when several faction views list them.

**Current full-game support is not certified.** Fieldability requires a legal selected roster, current points and equipment, accepted model geometry, and successful engine validation. Playability additionally requires every selected rule to execute; replay verification is a separate gate. A source page or a loaded module does not establish these properties.

Repository matches below are reconciliation candidates. `E` means the baseline report classifies a source row as executable; `Source` means recorded without that classification; `Missing` means no matching row. `E` can coexist with partial or source-only labels in other reports (F-EVID-01). **All require current-source verification.** Exact source-ID reconciliation is F01; matching names do not transfer runtime support.

## Army rules

**Current headings:** Drones; For the Greater Good.

Guided/Observer relationships affect shooting. Each drone type and its allocation must also be represented.

[Current army rules](https://www.40k.app/factions/tau-empire/army-rules)

| Existing army-rule record | Baseline evidence | Current work |
| --- | --- | --- |
| For the Greater Good | E; source label: engine_consumed | Compare every current clause; F02 |

## Latest changes to reconcile

- [Version 931 changes](https://www.40k.app/931/factions/tau-empire/updates): 19 linked changed items before support-scope filtering; use the detailed audit for the in-scope comparison.

## Detachments

DP is a detachment budget, separate from unit/Enhancement points and Stratagem CP. Rule names, force disposition, and complete Enhancement/Stratagem inventories are in the linked audit.

| Detachment | DP / force disposition | Rule headings | Baseline rule | Enh. / Strat. |
| --- | --- | --- | --- | --- |
| [Advanced Acquisition Cadre](../audit/tau-empire.md#detachment-advanced-acquisition-cadre) | 1 DP · Reconnaissance | expert fieldcraft | Source | 2 / 3 |
| [Auxiliary Cadre](../audit/tau-empire.md#detachment-auxiliary-cadre) | 1 DP · Disruption · Auxiliary | Integrated Command Structure | Missing | 2 / 3 |
| [Experimental Prototype Cadre](../audit/tau-empire.md#detachment-experimental-prototype-cadre) | 1 DP · Priority Assets · Battlesuit | Superior Craftsmanship | Source | 3 / 1 |
| [Kauyon](../audit/tau-empire.md#detachment-kauyon) | 2 DP · Reconnaissance | Patient Hunter | Source | 4 / 6 |
| [Kroot Hunting Pack](../audit/tau-empire.md#detachment-kroot-hunting-pack) | 2 DP · Take and Hold · Auxiliary | Keywords; Hunter’s Instincts; Skirmish Fighters | Source | 4 / 6 |
| [Mont’ka](../audit/tau-empire.md#detachment-montka) | 3 DP · Priority Assets | Killing Blow | Source | 4 / 6 |
| [Retaliation Cadre](../audit/tau-empire.md#detachment-retaliation-cadre) | 3 DP · Purge the Foe · Battlesuit | Bonded Heroes | Source | 4 / 6 |

## Datasheets and points

Costs below retain all displayed model-count tiers, repeat-unit surcharges, and equipment costs. They are an observed reference, not an engine pricing certificate. Open a unit audit for wargear, composition, bases, keywords, Leadership/Support, and abilities.

| Datasheet | Current costs | Repository component evidence |
| --- | --- | --- |
| [Breacher Team](../audit/tau-empire.md#unit-breacher-team) | 10 models 90 pts | No component row |
| [Broadside Battlesuits](../audit/tau-empire.md#unit-broadside-battlesuits) | 1 model 75 pts; 2 models 150 pts; 3 models 255 pts; 3rd+ in your army + 20 pts; High-yield missile pods + 5 pts | No component row |
| [Cadre Fireblade](../audit/tau-empire.md#unit-cadre-fireblade) | 1 model 50 pts | No component row |
| [Commander Farsight](../audit/tau-empire.md#unit-commander-farsight) | 1 model 70 pts | No component row |
| [Commander in Coldstar Battlesuit](../audit/tau-empire.md#unit-commander-in-coldstar-battlesuit) | 1 model 95 pts | No component row |
| [Commander in Enforcer Battlesuit](../audit/tau-empire.md#unit-commander-in-enforcer-battlesuit) | 1 model 80 pts | No component row |
| [Commander Shadowsun](../audit/tau-empire.md#unit-commander-shadowsun) | 1 model 100 pts | No component row |
| [Crisis Fireknife Battlesuits](../audit/tau-empire.md#unit-crisis-fireknife-battlesuits) | 3 models 100 pts; 3rd+ in your army + 10 pts; Missile pod + 5 pts | No component row |
| [Crisis Starscythe Battlesuits](../audit/tau-empire.md#unit-crisis-starscythe-battlesuits) | 3 models 100 pts; 3rd+ in your army + 10 pts; T’au flamer + 5 pts | No component row |
| [Crisis Sunforge Battlesuits](../audit/tau-empire.md#unit-crisis-sunforge-battlesuits) | 3 models 125 pts; 3rd+ in your army + 10 pts | No component row |
| [Darkstrider](../audit/tau-empire.md#unit-darkstrider) | 1 model 60 pts | No component row |
| [Devilfish](../audit/tau-empire.md#unit-devilfish) | 1 model 75 pts; 4th+ in your army + 10 pts | No component row |
| [Ethereal](../audit/tau-empire.md#unit-ethereal) | 1 model 50 pts | No component row |
| [Firesight Team](../audit/tau-empire.md#unit-firesight-team) | 1 model 55 pts | No component row |
| [Ghostkeel Battlesuit](../audit/tau-empire.md#unit-ghostkeel-battlesuit) | 1 model 150 pts; 3rd+ in your army + 15 pts; Cyclic ion raker + 15 pts | No component row |
| [Hammerhead Gunship](../audit/tau-empire.md#unit-hammerhead-gunship) | 1 model 150 pts; 3rd+ in your army + 10 pts | No component row |
| [Kroot Carnivores](../audit/tau-empire.md#unit-kroot-carnivores) | 10 models 65 pts; 20 models 130 pts | No component row |
| [Kroot Farstalkers](../audit/tau-empire.md#unit-kroot-farstalkers) | 12 models 75 pts; 3rd+ in your army + 10 pts | No component row |
| [Kroot Flesh Shaper](../audit/tau-empire.md#unit-kroot-flesh-shaper) | 1 model 45 pts | No component row |
| [Kroot Hounds](../audit/tau-empire.md#unit-kroot-hounds) | 5 models 45 pts; 10 models 65 pts | No component row |
| [Kroot Lone-spear](../audit/tau-empire.md#unit-kroot-lone-spear) | 1 model 80 pts | No component row |
| [Kroot Trail Shaper](../audit/tau-empire.md#unit-kroot-trail-shaper) | 1 model 50 pts | No component row |
| [Kroot War Shaper](../audit/tau-empire.md#unit-kroot-war-shaper) | 1 model 60 pts | No component row |
| [Krootox Rampagers](../audit/tau-empire.md#unit-krootox-rampagers) | 3 models 85 pts; 6 models 170 pts; 3rd+ in your army + 10 pts | No component row |
| [Krootox Riders](../audit/tau-empire.md#unit-krootox-riders) | 1 model 45 pts; 2 models 60 pts; 3 models 90 pts | No component row |
| [Pathfinder Team](../audit/tau-empire.md#unit-pathfinder-team) | 10 models 85 pts; 3rd+ in your army + 15 pts; Ion rifle + 5 pts | No component row |
| [Piranhas](../audit/tau-empire.md#unit-piranhas) | 1 model 65 pts; 2 models 110 pts; 3 models 165 pts; 3rd+ in your army + 10 pts | No component row |
| [Razorshark Strike Fighter](../audit/tau-empire.md#unit-razorshark-strike-fighter) | 1 model 160 pts | No component row |
| [Riptide Battlesuit](../audit/tau-empire.md#unit-riptide-battlesuit) | 1 model 190 pts; 3rd+ in your army + 30 pts; Ion accelerator + 25 pts | No component row |
| [Sky Ray Gunship](../audit/tau-empire.md#unit-sky-ray-gunship) | 1 model 140 pts | No component row |
| [Stealth Battlesuits](../audit/tau-empire.md#unit-stealth-battlesuits) | 5 models 100 pts; 3rd+ in your army + 10 pts | No component row |
| [Stormsurge](../audit/tau-empire.md#unit-stormsurge) | 1 model 375 pts; 2nd+ in your army + 25 pts | No component row |
| [Strike Team](../audit/tau-empire.md#unit-strike-team) | 10 models 70 pts | No component row |
| [Sun Shark Bomber](../audit/tau-empire.md#unit-sun-shark-bomber) | 1 model 150 pts | No component row |
| [Ta’unar Supremacy Armour](../audit/tau-empire.md#unit-taunar-supremacy-armour) | 1 model 790 pts; 2nd+ in your army + 100 pts | No component row |
| [The Twin Lance](../audit/tau-empire.md#unit-the-twin-lance) | 2 models 230 pts | No component row |
| [Tidewall Droneport](../audit/tau-empire.md#unit-tidewall-droneport) | 1 model 85 pts | No component row |
| [Tidewall Gunrig](../audit/tau-empire.md#unit-tidewall-gunrig) | 1 model 90 pts | No component row |
| [Tidewall Shieldline](../audit/tau-empire.md#unit-tidewall-shieldline) | 1 model 85 pts; 2 models 105 pts | No component row |
| [Vespid Stingwings](../audit/tau-empire.md#unit-vespid-stingwings) | 5 models 70 pts; 10 models 115 pts | No component row |

## Work remaining

1. **F00–F01:** retain approved source evidence, resolve scope and source IDs, and reconcile all updates since the July baseline.
2. **F02–F03:** certify army rules and implement the listed missing detachment rules, Enhancements, Upgrades, and Stratagems through generic services where possible.
3. **F04–F07:** reconcile every unit’s costs, composition, profiles, equipment options, geometry, keywords, attachments, and Core/Unit abilities. Each linked unit audit is an explicit open checklist.
4. **F08–F09:** exercise legal and invalid rosters through the shared adapter decision path, viewer projections, restore, replay, and full-game scenarios.

## Evidence

- [Detailed current-source inventory](../audit/tau-empire.md)
- [Source observation register](../../FACTION_AUDIT_SOURCES.md)
- [Generated historical evidence](../tau-empire.md)
- [Status definitions and acceptance checklist](../../FACTION_RULES_REMEDIATION_ROADMAP.md#status-and-acceptance-gates)
