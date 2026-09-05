# Chaos Knights: support and roadmap

[All factions](../../FACTION_SUPPORT.md) · [Roadmap](../../FACTION_RULES_REMEDIATION_ROADMAP.md) · [Detailed audit](../audit/chaos-knights.md)

Snapshot: 5 September 2026, 40k.app current view (latest published App-data version 946). Repository baseline: `52673fa1`.

## What can I use?

The current listing contains **11 in-scope datasheet references** and **8 detachment references**. 0 listed units have matching historical component-report rows. Shared source URLs are counted once in the audit, even when several faction views list them.

**Current full-game support is not certified.** Fieldability requires a legal selected roster, current points and equipment, accepted model geometry, and successful engine validation. Playability additionally requires every selected rule to execute; replay verification is a separate gate. A source page or a loaded module does not establish these properties.

Repository matches below are reconciliation candidates. `E` means the baseline report classifies a source row as executable; `Source` means recorded without that classification; `Missing` means no matching row. `E` can coexist with partial or source-only labels in other reports (F-EVID-01). **All require current-source verification.** Exact source-ID reconciliation is F01; matching names do not transfer runtime support.

## Army rules

**Current headings:** Harbingers of Dread; Super-heavy Walker; Dreadblades.

Dread effects interact with Battle-shock; also audit walker movement and Dreadblade army-construction rules.

[Current army rules](https://www.40k.app/factions/chaos-knights/army-rules)

| Existing army-rule record | Baseline evidence | Current work |
| --- | --- | --- |
| Harbingers of Dread | E; source label: engine_consumed | Compare every current clause; F02 |

## Latest changes to reconcile

- [Version 931 changes](https://www.40k.app/931/factions/chaos-knights/updates): 20 linked changed items before support-scope filtering; use the detailed audit for the in-scope comparison.

## Detachments

DP is a detachment budget, separate from unit/Enhancement points and Stratagem CP. Rule names, force disposition, and complete Enhancement/Stratagem inventories are in the linked audit.

| Detachment | DP / force disposition | Rule headings | Baseline rule | Enh. / Strat. |
| --- | --- | --- | --- | --- |
| [Bastions of Tyranny](../audit/chaos-knights.md#detachment-bastions-of-tyranny) | 1 DP · Priority Assets | Annihilate the Unworthy | Source | 2 / 3 |
| [Helhunt Lance](../audit/chaos-knights.md#detachment-helhunt-lance) | 2 DP · Disruption | Masters of the Pack | Source | 4 / 6 |
| [Houndpack Lance](../audit/chaos-knights.md#detachment-houndpack-lance) | 2 DP · Reconnaissance | Keywords; Marked Prey | Source | 4 / 6 |
| [Hunting Warpack](../audit/chaos-knights.md#detachment-hunting-warpack) | 1 DP · Reconnaissance | Scenting Fear | Source | 2 / 3 |
| [Iconoclast Fiefdom](../audit/chaos-knights.md#detachment-iconoclast-fiefdom) | 1 DP · Take and Hold | Wretched Thralls | Source | 2 / 3 |
| [Infernal Lance](../audit/chaos-knights.md#detachment-infernal-lance) | 3 DP · Priority Assets | Malefic Surge | Source | 4 / 6 |
| [Lords of Dread](../audit/chaos-knights.md#detachment-lords-of-dread) | 2 DP · Take and Hold | Tyrannical Court | Source | 6 / 6 |
| [Traitoris Lance](../audit/chaos-knights.md#detachment-traitoris-lance) | 2 DP · Purge the Foe | Paragons of Terror | Source | 4 / 6 |

## Datasheets and points

Costs below retain all displayed model-count tiers, repeat-unit surcharges, and equipment costs. They are an observed reference, not an engine pricing certificate. Open a unit audit for wargear, composition, bases, keywords, Leadership/Support, and abilities.

| Datasheet | Current costs | Repository component evidence |
| --- | --- | --- |
| [Knight Abominant](../audit/chaos-knights.md#unit-knight-abominant) | 1 model 355 pts; 3rd+ in your army + 15 pts | No component row |
| [Knight Desecrator](../audit/chaos-knights.md#unit-knight-desecrator) | 1 model 355 pts; 3rd+ in your army + 15 pts | No component row |
| [Knight Despoiler](../audit/chaos-knights.md#unit-knight-despoiler) | 1 model 360 pts; 2nd+ in your army + 30 pts; Despoiler battle cannon + 10 pts; Despoiler gatling cannon + 25 pts | No component row |
| [Knight Rampager](../audit/chaos-knights.md#unit-knight-rampager) | 1 model 355 pts; 3rd+ in your army + 15 pts | No component row |
| [Knight Ruinator](../audit/chaos-knights.md#unit-knight-ruinator) | 1 model 340 pts; 3rd+ in your army + 15 pts | No component row |
| [Knight Tyrant](../audit/chaos-knights.md#unit-knight-tyrant) | 1 model 400 pts; 2nd+ in your army + 20 pts | No component row |
| [War Dog Brigand](../audit/chaos-knights.md#unit-war-dog-brigand) | 1 model 135 pts | No component row |
| [War Dog Executioner](../audit/chaos-knights.md#unit-war-dog-executioner) | 1 model 130 pts | No component row |
| [War Dog Huntsman](../audit/chaos-knights.md#unit-war-dog-huntsman) | 1 model 135 pts | No component row |
| [War Dog Karnivore](../audit/chaos-knights.md#unit-war-dog-karnivore) | 1 model 145 pts | No component row |
| [War Dog Stalker](../audit/chaos-knights.md#unit-war-dog-stalker) | 1 model 135 pts | No component row |

## Work remaining

1. **F00–F01:** retain approved source evidence, resolve scope and source IDs, and reconcile all updates since the July baseline.
2. **F02–F03:** certify army rules and implement the listed missing detachment rules, Enhancements, Upgrades, and Stratagems through generic services where possible.
3. **F04–F07:** reconcile every unit’s costs, composition, profiles, equipment options, geometry, keywords, attachments, and Core/Unit abilities. Each linked unit audit is an explicit open checklist.
4. **F08–F09:** exercise legal and invalid rosters through the shared adapter decision path, viewer projections, restore, replay, and full-game scenarios.

## Evidence

- [Detailed current-source inventory](../audit/chaos-knights.md)
- [Source observation register](../../FACTION_AUDIT_SOURCES.md)
- [Generated historical evidence](../chaos-knights.md)
- [Status definitions and acceptance checklist](../../FACTION_RULES_REMEDIATION_ROADMAP.md#status-and-acceptance-gates)
