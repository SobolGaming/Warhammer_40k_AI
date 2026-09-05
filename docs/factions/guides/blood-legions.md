# Blood Legions: support and roadmap

[All factions](../../FACTION_SUPPORT.md) · [Roadmap](../../FACTION_RULES_REMEDIATION_ROADMAP.md) · [Detailed audit](../audit/blood-legions.md)

Snapshot: 5 September 2026, 40k.app current view (latest published App-data version 946). Repository baseline: `52673fa1`.

## What can I use?

The current listing contains **30 in-scope datasheet references** and **8 detachment references**. 2 listed units have matching historical component-report rows. Shared source URLs are counted once in the audit, even when several faction views list them.

**Current full-game support is not certified.** Fieldability requires a legal selected roster, current points and equipment, accepted model geometry, and successful engine validation. Playability additionally requires every selected rule to execute; replay verification is a separate gate. A source page or a loaded module does not establish these properties.

Repository matches below are reconciliation candidates. `E` means the baseline report classifies a source row as executable; `Source` means recorded without that classification; `Missing` means no matching row. `E` can coexist with partial or source-only labels in other reports (F-EVID-01). **All require current-source verification.** Exact source-ID reconciliation is F01; matching names do not transfer runtime support.

## Army rules

**Current headings:** Pact of Blood; Blessings of Khorne.

Blessings of Khorne selects benefits from a shared dice result. Audit combinations, resource use, and all six named blessings.

[Current army rules](https://www.40k.app/factions/blood-legions/army-rules)

| Existing army-rule record | Baseline evidence | Current work |
| --- | --- | --- |
| Blessings of Khorne | E; source label: engine_consumed | Compare every current clause; F02 |

This is a related faction/chapter view. Baseline evidence is filed under `world-eaters`; that grouping does not prove eligibility or substitute one datasheet for another.

## Latest changes to reconcile

- [Version 931 changes](https://www.40k.app/931/factions/blood-legions/updates): 2 linked changed items before support-scope filtering; use the detailed audit for the in-scope comparison.

## Detachments

DP is a detachment budget, separate from unit/Enhancement points and Stratagem CP. Rule names, force disposition, and complete Enhancement/Stratagem inventories are in the linked audit.

| Detachment | DP / force disposition | Rule headings | Baseline rule | Enh. / Strat. |
| --- | --- | --- | --- | --- |
| [Khorne Daemonkin](../audit/blood-legions.md#detachment-khorne-daemonkin) | 2 DP · Reconnaissance | Restrictions; Blood Tithe | Source | 4 / 6 |
| [Berzerker Warband](../audit/blood-legions.md#detachment-berzerker-warband) | 3 DP · Purge the Foe | Relentless Rage | Source | 4 / 6 |
| [Brazen Engines](../audit/blood-legions.md#detachment-brazen-engines) | 1 DP · Disruption | Rampaging Terrors | Source | 2 / 3 |
| [Butchers of Khorne](../audit/blood-legions.md#detachment-butchers-of-khorne) | 1 DP · Take and Hold | Adamantine Avalanche | Source | 2 / 3 |
| [Cult of Blood](../audit/blood-legions.md#detachment-cult-of-blood) | 2 DP · Priority Assets | Keywords; Idols of Khorne | Source | 4 / 6 |
| [Goretrack Onslaught](../audit/blood-legions.md#detachment-goretrack-onslaught) | 2 DP · Take and Hold | Rush to the Fray | Source | 4 / 6 |
| [Possessed Slaughterband](../audit/blood-legions.md#detachment-possessed-slaughterband) | 2 DP · Purge the Foe | Brazen Fury | Source | 4 / 6 |
| [Vessels of Wrath](../audit/blood-legions.md#detachment-vessels-of-wrath) | 1 DP · Priority Assets | Wrath of Khorne | Source | 2 / 3 |

## Datasheets and points

Costs below retain all displayed model-count tiers, repeat-unit surcharges, and equipment costs. They are an observed reference, not an engine pricing certificate. Open a unit audit for wargear, composition, bases, keywords, Leadership/Support, and abilities.

| Datasheet | Current costs | Repository component evidence |
| --- | --- | --- |
| [Bloodcrushers](../audit/blood-legions.md#unit-bloodcrushers) | 3 models 95 pts; 6 models 190 pts; 3rd+ in your army + 20 pts | No component row |
| [Bloodletters](../audit/blood-legions.md#unit-bloodletters) | 10 models 90 pts | No component row |
| [Bloodthirster](../audit/blood-legions.md#unit-bloodthirster) | 1 model 320 pts; 3rd+ in your army + 15 pts | No component row |
| [Flesh Hounds](../audit/blood-legions.md#unit-flesh-hounds) | 5 models 75 pts; 10 models 150 pts | No component row |
| [Skarbrand](../audit/blood-legions.md#unit-skarbrand) | 1 model 315 pts | No component row |

<details><summary>Shared datasheets — 25 additional source references and their costs</summary>

These entries link to their source-owning audit. Shared listing does not bypass faction, chapter, ally or detachment eligibility checks.

| Datasheet | Current costs | Repository component evidence |
| --- | --- | --- |
| [Angron](../audit/world-eaters.md#unit-angron) | 1 model 330 pts | No component row |
| [Chaos Land Raider](../audit/world-eaters.md#unit-chaos-land-raider) | 1 model 220 pts; 3rd+ in your army + 20 pts | No component row |
| [Chaos Predator Annihilator](../audit/world-eaters.md#unit-chaos-predator-annihilator) | 1 model 130 pts; 3rd+ in your army + 10 pts | No component row |
| [Chaos Predator Destructor](../audit/world-eaters.md#unit-chaos-predator-destructor) | 1 model 130 pts; 3rd+ in your army + 10 pts | No component row |
| [Chaos Rhino](../audit/world-eaters.md#unit-chaos-rhino) | 1 model 75 pts; 4th+ in your army + 10 pts | No component row |
| [Chaos Spawn](../audit/world-eaters.md#unit-chaos-spawn) | 2 models 95 pts | No component row |
| [Chaos Terminators](../audit/world-eaters.md#unit-chaos-terminators) | 5 models 165 pts; 10 models 330 pts; 3rd+ in your army + 10 pts | No component row |
| [Daemon Prince of Khorne](../audit/world-eaters.md#unit-daemon-prince-of-khorne) | 1 model 200 pts | No component row |
| [Daemon Prince of Khorne with Wings](../audit/world-eaters.md#unit-daemon-prince-of-khorne-with-wings) | 1 model 170 pts | No component row |
| [Defiler](../audit/world-eaters.md#unit-defiler) | 1 model 270 pts; 2nd+ in your army + 40 pts; Hades lascannon + 15 pts; Heavy reaper autocannon + 15 pts | Components evidenced; recheck |
| [Eightbound](../audit/world-eaters.md#unit-eightbound) | 3 models 125 pts; 6 models 255 pts; 3rd+ in your army + 15 pts | No component row |
| [Exalted Eightbound](../audit/world-eaters.md#unit-exalted-eightbound) | 3 models 130 pts; 6 models 265 pts; 3rd+ in your army + 15 pts | No component row |
| [Forgefiend](../audit/world-eaters.md#unit-forgefiend) | 1 model 140 pts; 3rd+ in your army + 15 pts; Ectoplasma cannon + 5 pts | No component row |
| [Goremongers](../audit/world-eaters.md#unit-goremongers) | 8 models 75 pts | No component row |
| [Helbrute](../audit/world-eaters.md#unit-helbrute) | 1 model 120 pts | No component row |
| [Heldrake](../audit/world-eaters.md#unit-heldrake) | 1 model 175 pts | No component row |
| [Jakhals](../audit/world-eaters.md#unit-jakhals) | 10 models 65 pts; 20 models 130 pts | No component row |
| [Khorne Berzerkers](../audit/world-eaters.md#unit-khorne-berzerkers) | 10 models 160 pts; 20 models 320 pts | No component row |
| [Khorne Lord of Skulls](../audit/world-eaters.md#unit-khorne-lord-of-skulls) | 1 model 505 pts; 2nd+ in your army + 30 pts | No component row |
| [Khârn the Betrayer](../audit/world-eaters.md#unit-kharn-the-betrayer) | 1 model 115 pts | No component row |
| [Lord Invocatus](../audit/world-eaters.md#unit-lord-invocatus) | 1 model 100 pts | No component row |
| [Lord on Juggernaut](../audit/world-eaters.md#unit-lord-on-juggernaut) | 1 model 95 pts | No component row |
| [Master of Executions](../audit/world-eaters.md#unit-master-of-executions) | 1 model 60 pts | No component row |
| [Maulerfiend](../audit/world-eaters.md#unit-maulerfiend) | 1 model 140 pts; 3rd+ in your army + 10 pts | Components evidenced; recheck |
| [Slaughterbound](../audit/world-eaters.md#unit-slaughterbound) | 1 model 100 pts | No component row |

</details>

## Work remaining

1. **F00–F01:** retain approved source evidence, resolve scope and source IDs, and reconcile all updates since the July baseline.
2. **F02–F03:** certify army rules and implement the listed missing detachment rules, Enhancements, Upgrades, and Stratagems through generic services where possible.
3. **F04–F07:** reconcile every unit’s costs, composition, profiles, equipment options, geometry, keywords, attachments, and Core/Unit abilities. Each linked unit audit is an explicit open checklist.
4. **F08–F09:** exercise legal and invalid rosters through the shared adapter decision path, viewer projections, restore, replay, and full-game scenarios.

## Evidence

- [Detailed current-source inventory](../audit/blood-legions.md)
- [Source observation register](../../FACTION_AUDIT_SOURCES.md)
- [Generated historical evidence](../world-eaters.md)
- [Status definitions and acceptance checklist](../../FACTION_RULES_REMEDIATION_ROADMAP.md#status-and-acceptance-gates)
