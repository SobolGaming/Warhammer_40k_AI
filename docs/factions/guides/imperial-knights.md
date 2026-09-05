# Imperial Knights: support and roadmap

[All factions](../../FACTION_SUPPORT.md) · [Roadmap](../../FACTION_RULES_REMEDIATION_ROADMAP.md) · [Detailed audit](../audit/imperial-knights.md)

Snapshot: 5 September 2026, 40k.app current view (latest published App-data version 946). Repository baseline: `52673fa1`.

## What can I use?

The current listing contains **14 in-scope datasheet references** and **8 detachment references**. 0 listed units have matching historical component-report rows. Shared source URLs are counted once in the audit, even when several faction views list them.

**Current full-game support is not certified.** Fieldability requires a legal selected roster, current points and equipment, accepted model geometry, and successful engine validation. Playability additionally requires every selected rule to execute; replay verification is a separate gate. A source page or a loaded module does not establish these properties.

Repository matches below are reconciliation candidates. `E` means the baseline report classifies a source row as executable; `Source` means recorded without that classification; `Missing` means no matching row. `E` can coexist with partial or source-only labels in other reports (F-EVID-01). **All require current-source verification.** Exact source-ID reconciliation is F01; matching names do not transfer runtime support.

## Army rules

**Current headings:** Code Chivalric; Bondsman; Super-heavy Walker; Freeblades.

Code Chivalric tracks deeds and qualities; Bondsman links units. Walker movement and Freeblade inclusion also need independent checks.

[Current army rules](https://www.40k.app/factions/imperial-knights/army-rules)

| Existing army-rule record | Baseline evidence | Current work |
| --- | --- | --- |
| Code Chivalric | E; source label: engine_consumed | Compare every current clause; F02 |

## Latest changes to reconcile

- [Version 931 changes](https://www.40k.app/931/factions/imperial-knights/updates): 22 linked changed items before support-scope filtering; use the detailed audit for the in-scope comparison.

## Detachments

DP is a detachment budget, separate from unit/Enhancement points and Stratagem CP. Rule names, force disposition, and complete Enhancement/Stratagem inventories are in the linked audit.

| Detachment | DP / force disposition | Rule headings | Baseline rule | Enh. / Strat. |
| --- | --- | --- | --- | --- |
| [Dominus Foebreakers](../audit/imperial-knights.md#detachment-dominus-foebreakers) | 1 DP · Priority Assets | Rain of Devastation | Source | 2 / 3 |
| [Freeblade Company](../audit/imperial-knights.md#detachment-freeblade-company) | 3 DP · Priority Assets | Knights of Legend | Source | 4 / 6 |
| [Gate Warden Lance](../audit/imperial-knights.md#detachment-gate-warden-lance) | 2 DP · Take and Hold | Dauntless Defenders | Source | 4 / 6 |
| [Questor Forgepact](../audit/imperial-knights.md#detachment-questor-forgepact) | 1 DP · Disruption | Cogbound Alliance | Source | 2 / 3 |
| [Questoris Companions](../audit/imperial-knights.md#detachment-questoris-companions) | 3 DP · Take and Hold | Heroes of Legend; Valour’s Reward | Source | 4 / 6 |
| [Spearhead-at-Arms](../audit/imperial-knights.md#detachment-spearhead-at-arms) | 2 DP · Reconnaissance · Armigers | KEYWORDS; Knightly Teachings | Source | 4 / 6 |
| [Throne-bonded Outriders](../audit/imperial-knights.md#detachment-throne-bonded-outriders) | 1 DP · Reconnaissance · Armigers | Driven from their Lairs | Source | 2 / 3 |
| [Valourstrike Lance](../audit/imperial-knights.md#detachment-valourstrike-lance) | 2 DP · Purge the Foe | Bold Gallantry | Source | 4 / 6 |

## Datasheets and points

Costs below retain all displayed model-count tiers, repeat-unit surcharges, and equipment costs. They are an observed reference, not an engine pricing certificate. Open a unit audit for wargear, composition, bases, keywords, Leadership/Support, and abilities.

| Datasheet | Current costs | Repository component evidence |
| --- | --- | --- |
| [Armiger Helverin](../audit/imperial-knights.md#unit-armiger-helverin) | 1 model 140 pts | No component row |
| [Armiger Warglaive](../audit/imperial-knights.md#unit-armiger-warglaive) | 1 model 140 pts | No component row |
| [Canis Rex](../audit/imperial-knights.md#unit-canis-rex) | 1 model 415 pts | No component row |
| [Knight Castellan](../audit/imperial-knights.md#unit-knight-castellan) | 1 model 425 pts; 2nd+ in your army + 25 pts | No component row |
| [Knight Crusader](../audit/imperial-knights.md#unit-knight-crusader) | 1 model 395 pts; 2nd+ in your army + 20 pts; Rapid-fire battle cannon + 15 pts | No component row |
| [Knight Defender](../audit/imperial-knights.md#unit-knight-defender) | 1 model 400 pts; 2nd+ in your army + 20 pts | No component row |
| [Knight Destrier](../audit/imperial-knights.md#unit-knight-destrier) | 1 model 265 pts; 3rd+ in your army + 15 pts | No component row |
| [Knight Errant](../audit/imperial-knights.md#unit-knight-errant) | 1 model 355 pts; 3rd+ in your army + 15 pts | No component row |
| [Knight Gallant](../audit/imperial-knights.md#unit-knight-gallant) | 1 model 355 pts; 3rd+ in your army + 15 pts | No component row |
| [Knight Paladin](../audit/imperial-knights.md#unit-knight-paladin) | 1 model 375 pts; 3rd+ in your army + 15 pts | No component row |
| [Knight Preceptor](../audit/imperial-knights.md#unit-knight-preceptor) | 1 model 365 pts; 3rd+ in your army + 15 pts | No component row |
| [Knight Valiant](../audit/imperial-knights.md#unit-knight-valiant) | 1 model 400 pts; 3rd+ in your army + 15 pts | No component row |
| [Knight Warden](../audit/imperial-knights.md#unit-knight-warden) | 1 model 375 pts; 3rd+ in your army + 15 pts | No component row |
| [Sir Hekhtur](../audit/imperial-knights.md#unit-sir-hekhtur) | No standalone cost shown; inspect inclusion rule | No component row |

## Work remaining

1. **F00–F01:** retain approved source evidence, resolve scope and source IDs, and reconcile all updates since the July baseline.
2. **F02–F03:** certify army rules and implement the listed missing detachment rules, Enhancements, Upgrades, and Stratagems through generic services where possible.
3. **F04–F07:** reconcile every unit’s costs, composition, profiles, equipment options, geometry, keywords, attachments, and Core/Unit abilities. Each linked unit audit is an explicit open checklist.
4. **F08–F09:** exercise legal and invalid rosters through the shared adapter decision path, viewer projections, restore, replay, and full-game scenarios.

## Evidence

- [Detailed current-source inventory](../audit/imperial-knights.md)
- [Source observation register](../../FACTION_AUDIT_SOURCES.md)
- [Generated historical evidence](../imperial-knights.md)
- [Status definitions and acceptance checklist](../../FACTION_RULES_REMEDIATION_ROADMAP.md#status-and-acceptance-gates)
