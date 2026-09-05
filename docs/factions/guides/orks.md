# Orks: support and roadmap

[All factions](../../FACTION_SUPPORT.md) · [Roadmap](../../FACTION_RULES_REMEDIATION_ROADMAP.md) · [Detailed audit](../audit/orks.md)

Snapshot: 5 September 2026, 40k.app current view (latest published App-data version 946). Repository baseline: `52673fa1`.

## What can I use?

The current listing contains **53 in-scope datasheet references** and **15 detachment references**. 0 listed units have matching historical component-report rows. Shared source URLs are counted once in the audit, even when several faction views list them.

**Current full-game support is not certified.** Fieldability requires a legal selected roster, current points and equipment, accepted model geometry, and successful engine validation. Playability additionally requires every selected rule to execute; replay verification is a separate gate. A source page or a loaded module does not establish these properties.

Repository matches below are reconciliation candidates. `E` means the baseline report classifies a source row as executable; `Source` means recorded without that classification; `Missing` means no matching row. `E` can coexist with partial or source-only labels in other reports (F-EVID-01). **All require current-source verification.** Exact source-ID reconciliation is F01; matching names do not transfer runtime support.

## Army rules

**Current headings:** Waaagh!; Da Boss; Unstable energies; Special Move Types.

The v946 refresh changes the army and detachment baseline. Waaagh!, Da Boss, unstable-energy rules, and special moves need a new source comparison.

[Current army rules](https://www.40k.app/factions/orks/army-rules)

| Existing army-rule record | Baseline evidence | Current work |
| --- | --- | --- |
| Waaagh! | E; source label: engine_consumed | Compare every current clause; F02 |

**Confirmed drift:** v946 removes More Dakka! despite its implemented baseline status. It also replaces several units and detachments. Retire stale eligibility before reusing any old execution claim (F-ORK-01).

## Latest changes to reconcile

- [Version 946 changes](https://www.40k.app/factions/orks/updates): 81 linked changed items before support-scope filtering; use the detailed audit for the in-scope comparison.
- [Version 931 changes](https://www.40k.app/931/factions/orks/updates): 27 linked changed items before support-scope filtering; use the detailed audit for the in-scope comparison.

## Detachments

DP is a detachment budget, separate from unit/Enhancement points and Stratagem CP. Rule names, force disposition, and complete Enhancement/Stratagem inventories are in the linked audit.

| Detachment | DP / force disposition | Rule headings | Baseline rule | Enh. / Strat. |
| --- | --- | --- | --- | --- |
| [Blitz Brigade](../audit/orks.md#detachment-blitz-brigade) | 1 DP · Take and Hold | Unstoppable Momentum | Source | 2 / 3 |
| [Brute Bosses](../audit/orks.md#detachment-brute-bosses) | 1 DP · Purge the Foe | ’Ard as Nails | Missing | 6 / 0 |
| [Bully Boyz](../audit/orks.md#detachment-bully-boyz) | 1 DP · Purge the Foe | Displays of Savagery | Source | 2 / 3 |
| [Da Big Hunt](../audit/orks.md#detachment-da-big-hunt) | 1 DP · Purge the Foe | Da Hunt is On | Source | 2 / 3 |
| [Dread Mob](../audit/orks.md#detachment-dread-mob) | 1 DP · Purge the Foe | Try Dat Button! | Source | 2 / 3 |
| [Flyboyz](../audit/orks.md#detachment-flyboyz) | 1 DP · Reconnaissance | Skyborne Loons | Missing | 2 / 3 |
| [Green Tide](../audit/orks.md#detachment-green-tide) | 1 DP · Take and Hold | Mob-handed Brutality | Source | 2 / 3 |
| [Kult of Speed](../audit/orks.md#detachment-kult-of-speed) | 1 DP · Reconnaissance | Adrenaline Junkies | Source | 2 / 3 |
| [Madcap Meks](../audit/orks.md#detachment-madcap-meks) | 1 DP · Disruption | Unpredictable Genius | Missing | 3 / 1 |
| [Runt Swarm](../audit/orks.md#detachment-runt-swarm) | 1 DP · Priority Assets | Sneaky Little Gitz | Missing | 2 / 3 |
| [Shoota Boyz](../audit/orks.md#detachment-shoota-boyz) | 1 DP · Purge the Foe | Dakka! Dakka! Dakka! | Missing | 2 / 3 |
| [Taktikal Brigade](../audit/orks.md#detachment-taktikal-brigade) | 1 DP · Take and Hold | Suspiciously Well Organised | Source | 2 / 3 |
| [War Horde](../audit/orks.md#detachment-war-horde) | 3 DP · Take and Hold / Purge the Foe | Get Stuck In | Source | 4 / 6 |
| [Wreckas](../audit/orks.md#detachment-wreckas) | 1 DP · Priority Assets | Wreckin’ and Lootin’ | Missing | 2 / 3 |
| [Wurrband](../audit/orks.md#detachment-wurrband) | 1 DP · Disruption | Powers of da Waaagh! | Missing | 3 / 0 |

## Datasheets and points

Costs below retain all displayed model-count tiers, repeat-unit surcharges, and equipment costs. They are an observed reference, not an engine pricing certificate. Open a unit audit for wargear, composition, bases, keywords, Leadership/Support, and abilities.

| Datasheet | Current costs | Repository component evidence |
| --- | --- | --- |
| [Bannernob](../audit/orks.md#unit-bannernob) | 1 model 35 pts | No component row |
| [Battlewagon](../audit/orks.md#unit-battlewagon) | 1 model 150 pts; 3rd+ in your army + 10 pts | No component row |
| [Beast Snagga Boyz](../audit/orks.md#unit-beast-snagga-boyz) | 10 models 85 pts; 20 models 170 pts; 4th+ in your army + 10 pts | No component row |
| [Beastboss](../audit/orks.md#unit-beastboss) | 1 model 85 pts | No component row |
| [Beastboss on Squigosaur](../audit/orks.md#unit-beastboss-on-squigosaur) | 1 model 140 pts; 3rd+ in your army + 15 pts | No component row |
| [Big Mek](../audit/orks.md#unit-big-mek) | 1 model 85 pts; 3rd+ in your army + 10 pts | No component row |
| [Big Mek Dakkarig](../audit/orks.md#unit-big-mek-dakkarig) | 1 model 135 pts; 3rd+ in your army + 10 pts | No component row |
| [Big Mek in Mega Armour](../audit/orks.md#unit-big-mek-in-mega-armour) | 1 model 90 pts | No component row |
| [Big Mek with Shokk Attack Gun](../audit/orks.md#unit-big-mek-with-shokk-attack-gun) | 1 model 95 pts; 2nd+ in your army + 10 pts | No component row |
| [Bigboss](../audit/orks.md#unit-bigboss) | 1 model 50 pts | No component row |
| [Big’Ed Bossbunka](../audit/orks.md#unit-biged-bossbunka) | 1 model 135 pts | No component row |
| [Blitza‑bommer](../audit/orks.md#unit-blitza-bommer) | 1 model 115 pts | No component row |
| [Boss Snikrot](../audit/orks.md#unit-boss-snikrot) | 1 model 80 pts | No component row |
| [Boyz](../audit/orks.md#unit-boyz) | 10 models 90 pts; 20 models 180 pts; 4th+ in your army + 10 pts | No component row |
| [Breaka Boyz](../audit/orks.md#unit-breaka-boyz) | 6 models 135 pts; 3rd+ in your army + 10 pts | No component row |
| [Burna‑bommer](../audit/orks.md#unit-burna-bommer) | 1 model 125 pts | No component row |
| [Dakkajet](../audit/orks.md#unit-dakkajet) | 1 model 125 pts | No component row |
| [Deff Dread](../audit/orks.md#unit-deff-dread) | 1 model 130 pts; 3rd+ in your army + 10 pts | No component row |
| [Deffkilla Wartrike](../audit/orks.md#unit-deffkilla-wartrike) | 1 model 80 pts | No component row |
| [Deffkoptas](../audit/orks.md#unit-deffkoptas) | 3 models 80 pts; 6 models 160 pts; 3rd+ in your army + 10 pts | No component row |
| [Flash Gitz](../audit/orks.md#unit-flash-gitz) | 5 models 105 pts; 10 models 210 pts; 3rd+ in your army + 30 pts | No component row |
| [Ghazghkull Thraka](../audit/orks.md#unit-ghazghkull-thraka) | 1 model 300 pts | No component row |
| [Gorkanaut](../audit/orks.md#unit-gorkanaut) | 1 model 325 pts; 3rd+ in your army + 30 pts | No component row |
| [Gretchin](../audit/orks.md#unit-gretchin) | 10 models 45 pts; 20 models 80 pts | No component row |
| [Gunwagon](../audit/orks.md#unit-gunwagon) | 1 model 150 pts; 3rd+ in your army + 10 pts; Zzap Gun + 10 pts | No component row |
| [Hunta Rig](../audit/orks.md#unit-hunta-rig) | 1 model 165 pts; 3rd+ in your army + 10 pts | No component row |
| [Kill Rig](../audit/orks.md#unit-kill-rig) | 1 model 175 pts; 3rd+ in your army + 10 pts | No component row |
| [Killa Kans](../audit/orks.md#unit-killa-kans) | 3 models 130 pts; 6 models 260 pts; 3rd+ in your army + 20 pts | No component row |
| [Kommandos](../audit/orks.md#unit-kommandos) | 10 models 125 pts | No component row |
| [Meganobz](../audit/orks.md#unit-meganobz) | 2 models 75 pts; 3 models 110 pts; 5 models 185 pts; 6 models 225 pts; 3rd+ in your army + 40 pts; Twin Killsaws + 5 pts | No component row |
| [Mek](../audit/orks.md#unit-mek) | 1 model 45 pts | No component row |
| [Mek Gunz](../audit/orks.md#unit-mek-gunz) | 1 model 55 pts; 2 models 110 pts; 3 models 165 pts; 3rd+ in your army + 10 pts | No component row |
| [Morkanaut](../audit/orks.md#unit-morkanaut) | 1 model 345 pts; 3rd+ in your army + 30 pts | No component row |
| [Mozrog Skragbad](../audit/orks.md#unit-mozrog-skragbad) | 1 model 170 pts | No component row |
| [Nazdreg](../audit/orks.md#unit-nazdreg) | 1 model 175 pts | No component row |
| [Nobz](../audit/orks.md#unit-nobz) | 5 models 125 pts; 10 models 250 pts; 3rd+ in your army + 30 pts; Paired Krumpas + 5 pts | No component row |
| [Painboss](../audit/orks.md#unit-painboss) | 1 model 60 pts; 3rd+ in your army + 10 pts | No component row |
| [Painboy](../audit/orks.md#unit-painboy) | 1 model 45 pts | No component row |
| [Rukkatrukk Squigbuggies](../audit/orks.md#unit-rukkatrukk-squigbuggies) | 1 model 85 pts; 2 models 160 pts | No component row |
| [Runtherd](../audit/orks.md#unit-runtherd) | 1 model 10 pts | No component row |
| [Squighog Boyz](../audit/orks.md#unit-squighog-boyz) | 4 models 140 pts; 8 models 280 pts; 3rd+ in your army + 20 pts | No component row |
| [Stompa](../audit/orks.md#unit-stompa) | 1 model 700 pts; 2nd+ in your army + 100 pts | No component row |
| [Stormboyz](../audit/orks.md#unit-stormboyz) | 5 models 70 pts; 10 models 140 pts | No component row |
| [Tankbustas](../audit/orks.md#unit-tankbustas) | 6 models 145 pts; 3rd+ in your army + 10 pts | No component row |
| [Trukk](../audit/orks.md#unit-trukk) | 1 model 60 pts; 4th+ in your army + 10 pts | No component row |
| [Warbikers](../audit/orks.md#unit-warbikers) | 3 models 75 pts; 6 models 140 pts | No component row |
| [Warboss](../audit/orks.md#unit-warboss) | 1 model 100 pts | No component row |
| [Warboss in Mega Armour](../audit/orks.md#unit-warboss-in-mega-armour) | 1 model 125 pts; 3rd+ in your army + 15 pts | No component row |
| [Wartrakks](../audit/orks.md#unit-wartrakks) | 1 model 70 pts; 2 models 130 pts | No component row |
| [Wazbom Blastajet](../audit/orks.md#unit-wazbom-blastajet) | 1 model 215 pts; 3rd+ in your army + 20 pts | No component row |
| [Wazdakka Gutsmek](../audit/orks.md#unit-wazdakka-gutsmek) | 1 model 200 pts | No component row |
| [Weirdboy](../audit/orks.md#unit-weirdboy) | 1 model 65 pts | No component row |
| [Zodgrod Wortsnagga](../audit/orks.md#unit-zodgrod-wortsnagga) | 1 model 50 pts | No component row |

## Work remaining

1. **F00–F01:** retain approved source evidence, resolve scope and source IDs, and reconcile all updates since the July baseline.
2. **F02–F03:** certify army rules and implement the listed missing detachment rules, Enhancements, Upgrades, and Stratagems through generic services where possible.
3. **F04–F07:** reconcile every unit’s costs, composition, profiles, equipment options, geometry, keywords, attachments, and Core/Unit abilities. Each linked unit audit is an explicit open checklist.
4. **F08–F09:** exercise legal and invalid rosters through the shared adapter decision path, viewer projections, restore, replay, and full-game scenarios.

## Evidence

- [Detailed current-source inventory](../audit/orks.md)
- [Source observation register](../../FACTION_AUDIT_SOURCES.md)
- [Generated historical evidence](../orks.md)
- [Status definitions and acceptance checklist](../../FACTION_RULES_REMEDIATION_ROADMAP.md#status-and-acceptance-gates)
