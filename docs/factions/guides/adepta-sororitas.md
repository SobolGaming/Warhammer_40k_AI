# Adepta Sororitas: support and roadmap

[All factions](../../FACTION_SUPPORT.md) · [Roadmap](../../FACTION_RULES_REMEDIATION_ROADMAP.md) · [Detailed audit](../audit/adepta-sororitas.md)

Snapshot: 5 September 2026, 40k.app current view (latest published App-data version 946). Repository baseline: `52673fa1`.

## What can I use?

The current listing contains **33 in-scope datasheet references** and **8 detachment references**. 0 listed units have matching historical component-report rows. Shared source URLs are counted once in the audit, even when several faction views list them.

**Current full-game support is not certified.** Fieldability requires a legal selected roster, current points and equipment, accepted model geometry, and successful engine validation. Playability additionally requires every selected rule to execute; replay verification is a separate gate. A source page or a loaded module does not establish these properties.

Repository matches below are reconciliation candidates. `E` means the baseline report classifies a source row as executable; `Source` means recorded without that classification; `Missing` means no matching row. `E` can coexist with partial or source-only labels in other reports (F-EVID-01). **All require current-source verification.** Exact source-ID reconciliation is F01; matching names do not transfer runtime support.

## Army rules

**Current headings:** Acts of Faith.

A Miracle-dice pool supplies selected roll substitutions. Current gain timing differs from the implemented battle-round trigger (F-ARMY-01).

[Current army rules](https://www.40k.app/factions/adepta-sororitas/army-rules)

| Existing army-rule record | Baseline evidence | Current work |
| --- | --- | --- |
| Acts of Faith | E; source label: engine_consumed | Compare every current clause; F02 |

**Confirmed drift:** Miracle dice gain at each turn start in the App; the existing consumer triggers once at battle-round start (F-ARMY-01).

## Latest changes to reconcile

- [Version 931 changes](https://www.40k.app/931/factions/adepta-sororitas/updates): 11 linked changed items before support-scope filtering; use the detailed audit for the in-scope comparison.

## Detachments

DP is a detachment budget, separate from unit/Enhancement points and Stratagem CP. Rule names, force disposition, and complete Enhancement/Stratagem inventories are in the linked audit.

| Detachment | DP / force disposition | Rule headings | Baseline rule | Enh. / Strat. |
| --- | --- | --- | --- | --- |
| [Army of Faith](../audit/adepta-sororitas.md#detachment-army-of-faith) | 2 DP · Take and Hold | Sacred Rites | Source | 4 / 6 |
| [Bringers of Flame](../audit/adepta-sororitas.md#detachment-bringers-of-flame) | 2 DP · Priority Assets | Fervent Purgation | Source | 4 / 6 |
| [Champions of Faith](../audit/adepta-sororitas.md#detachment-champions-of-faith) | 2 DP · Disruption · Reverend | KEYWORDS; Righteous Purpose | Source | 4 / 6 |
| [Chorus of Condemnation](../audit/adepta-sororitas.md#detachment-chorus-of-condemnation) | 1 DP · Reconnaissance | Angelic Judgement | Source | 2 / 3 |
| [Hallowed Martyrs](../audit/adepta-sororitas.md#detachment-hallowed-martyrs) | 3 DP · Priority Assets | The Blood of Martyrs | Source | 4 / 6 |
| [Penitent Host](../audit/adepta-sororitas.md#detachment-penitent-host) | 2 DP · Purge the Foe | Desperate For Redemption | Source | 4 / 6 |
| [Sacred Champions](../audit/adepta-sororitas.md#detachment-sacred-champions) | 1 DP · Take and Hold · Reverend | Holy Quest | Source | 2 / 3 |
| [Sanctified Orators](../audit/adepta-sororitas.md#detachment-sanctified-orators) | 1 DP · Disruption | Hymns of Battle | Source | 1 / 0 |

## Datasheets and points

Costs below retain all displayed model-count tiers, repeat-unit surcharges, and equipment costs. They are an observed reference, not an engine pricing certificate. Open a unit audit for wargear, composition, bases, keywords, Leadership/Support, and abilities.

| Datasheet | Current costs | Repository component evidence |
| --- | --- | --- |
| [Aestred Thurga and Agathae Dolan](../audit/adepta-sororitas.md#unit-aestred-thurga-and-agathae-dolan) | 2 models 80 pts | No component row |
| [Arco-flagellants](../audit/adepta-sororitas.md#unit-arco-flagellants) | 3 models 50 pts; 10 models 140 pts | No component row |
| [Battle Sisters Squad](../audit/adepta-sororitas.md#unit-battle-sisters-squad) | 10 models 100 pts | No component row |
| [Canoness](../audit/adepta-sororitas.md#unit-canoness) | 1 model 60 pts | No component row |
| [Canoness with Jump Pack](../audit/adepta-sororitas.md#unit-canoness-with-jump-pack) | 1 model 75 pts | No component row |
| [Castigator](../audit/adepta-sororitas.md#unit-castigator) | 1 model 165 pts; 3rd+ in your army + 10 pts | No component row |
| [Celestian Insidiants](../audit/adepta-sororitas.md#unit-celestian-insidiants) | 10 models 120 pts | No component row |
| [Celestian Sacresants](../audit/adepta-sororitas.md#unit-celestian-sacresants) | 5 models 75 pts; 10 models 150 pts; 3rd+ in your army + 10 pts | No component row |
| [Daemonifuge](../audit/adepta-sororitas.md#unit-daemonifuge) | 2 models 85 pts | No component row |
| [Dialogus](../audit/adepta-sororitas.md#unit-dialogus) | 1 model 40 pts | No component row |
| [Dogmata](../audit/adepta-sororitas.md#unit-dogmata) | 1 model 45 pts | No component row |
| [Dominion Squad](../audit/adepta-sororitas.md#unit-dominion-squad) | 10 models 90 pts; 3rd+ in your army + 10 pts; Meltagun + 5 pts | No component row |
| [Exorcist](../audit/adepta-sororitas.md#unit-exorcist) | 1 model 180 pts; 2nd+ in your army + 40 pts | No component row |
| [Hospitaller](../audit/adepta-sororitas.md#unit-hospitaller) | 1 model 65 pts; 2nd+ in your army + 10 pts | No component row |
| [Imagifier](../audit/adepta-sororitas.md#unit-imagifier) | 1 model 55 pts | No component row |
| [Immolator](../audit/adepta-sororitas.md#unit-immolator) | 1 model 100 pts; 4th+ in your army + 15 pts; Twin multi-melta + 15 pts | No component row |
| [Intranzia Fraye](../audit/adepta-sororitas.md#unit-intranzia-fraye) | 1 model 135 pts | No component row |
| [Junith Eruita](../audit/adepta-sororitas.md#unit-junith-eruita) | 1 model 105 pts | No component row |
| [Ministorum Priest](../audit/adepta-sororitas.md#unit-ministorum-priest) | 1 model 50 pts | No component row |
| [Mortifiers](../audit/adepta-sororitas.md#unit-mortifiers) | 1 model 70 pts; 2 models 130 pts | No component row |
| [Morvenn Vahl](../audit/adepta-sororitas.md#unit-morvenn-vahl) | 1 model 200 pts | No component row |
| [Palatine](../audit/adepta-sororitas.md#unit-palatine) | 1 model 50 pts | No component row |
| [Paragon Warsuits](../audit/adepta-sororitas.md#unit-paragon-warsuits) | 3 models 180 pts; 3rd+ in your army + 10 pts; Multi-melta + 10 pts | No component row |
| [Penitent Engines](../audit/adepta-sororitas.md#unit-penitent-engines) | 1 model 70 pts; 2 models 140 pts | No component row |
| [Repentia Squad](../audit/adepta-sororitas.md#unit-repentia-squad) | 5 models 70 pts; 10 models 140 pts | No component row |
| [Retributor Squad](../audit/adepta-sororitas.md#unit-retributor-squad) | 5 models 105 pts; 3rd+ in your army + 10 pts; Multi-melta + 5 pts | No component row |
| [Saint Celestine](../audit/adepta-sororitas.md#unit-saint-celestine) | 3 models 150 pts | No component row |
| [Sanctifiers](../audit/adepta-sororitas.md#unit-sanctifiers) | 9 models 110 pts | No component row |
| [Seraphim Squad](../audit/adepta-sororitas.md#unit-seraphim-squad) | 5 models 75 pts; 10 models 150 pts; 3rd+ in your army + 10 pts | No component row |
| [Sisters Novitiate Squad](../audit/adepta-sororitas.md#unit-sisters-novitiate-squad) | 10 models 90 pts | No component row |
| [Sororitas Rhino](../audit/adepta-sororitas.md#unit-sororitas-rhino) | 1 model 65 pts; 4th+ in your army + 10 pts | No component row |
| [Triumph of Saint Katherine](../audit/adepta-sororitas.md#unit-triumph-of-saint-katherine) | 1 model 245 pts | No component row |
| [Zephyrim Squad](../audit/adepta-sororitas.md#unit-zephyrim-squad) | 5 models 75 pts; 10 models 150 pts; 3rd+ in your army + 10 pts | No component row |

## Work remaining

1. **F00–F01:** retain approved source evidence, resolve scope and source IDs, and reconcile all updates since the July baseline.
2. **F02–F03:** certify army rules and implement the listed missing detachment rules, Enhancements, Upgrades, and Stratagems through generic services where possible.
3. **F04–F07:** reconcile every unit’s costs, composition, profiles, equipment options, geometry, keywords, attachments, and Core/Unit abilities. Each linked unit audit is an explicit open checklist.
4. **F08–F09:** exercise legal and invalid rosters through the shared adapter decision path, viewer projections, restore, replay, and full-game scenarios.

## Evidence

- [Detailed current-source inventory](../audit/adepta-sororitas.md)
- [Source observation register](../../FACTION_AUDIT_SOURCES.md)
- [Generated historical evidence](../adepta-sororitas.md)
- [Status definitions and acceptance checklist](../../FACTION_RULES_REMEDIATION_ROADMAP.md#status-and-acceptance-gates)
