# Faction support: start here

[Remediation roadmap](FACTION_RULES_REMEDIATION_ROADMAP.md) · [Source observations and limits](FACTION_AUDIT_SOURCES.md)

**Choose a faction below for army rules, detachments, all displayed unit costs, and the work needed for full support.** Each guide links to expandable unit and detachment audits. Snapshot: **5 September 2026**, latest observed App-data version **946**; repository baseline **`52673fa1`**.

## What is supported today?

The repository has implemented rule consumers and partial component coverage, but this audit does **not certify a current full-game roster or faction**. A unit appearing in a source catalog is insufficient to call it fieldable or playable. The older component report calls 56 of its 59 rows `Playable`; that is a historical component label and must not be interpreted as current complete gameplay support.

- **Fieldable:** the selected roster passes current costs, composition, equipment, attachments, faction/detachment restrictions and accepted geometry.
- **Playable:** all rules of that fieldable roster execute through the engine decision path.
- **Replay verified:** those decisions and effects survive serialization, restore, viewer redaction and replay.
- **Full support:** all legal variants and required branches have the preceding evidence for a pinned source version.

The [acceptance gates](FACTION_RULES_REMEDIATION_ROADMAP.md#status-and-acceptance-gates) define the evidence needed for each claim. The guides show baseline executable classifications, recorded source rows and missing matches separately; all require current-source reconciliation.

## Faction directory

The 40 rows are source views, including six additional Marine chapters and six related armies. They map to the repository’s 28 faction reporting groups; they do not establish 40 independent engine factions. “Listed / owned” counts unit links in that view and source URLs owned by it. Shared unit links open the owning audit. Detachment counts also include inherited views and must not be summed as unique rules.

| Faction / source view | Current army-rule headings | Units: listed / owned | Detachment pages |
| --- | --- | --- | --- |
| [Adepta Sororitas](factions/guides/adepta-sororitas.md) | Acts of Faith | 33 / 33 | 8 |
| [Adeptus Custodes](factions/guides/adeptus-custodes.md) | Martial Ka’tah | 18 / 18 | 9 |
| [Adeptus Mechanicus](factions/guides/adeptus-mechanicus.md) | Doctrina Imperatives | 34 / 34 | 10 |
| [Aeldari](factions/guides/aeldari.md) | Battle Focus; Disparate Paths | 55 / 55 | 14 |
| [Astra Militarum](factions/guides/astra-militarum.md) | Voice of Command | 70 / 70 | 11 |
| [Black Templars](factions/guides/black-templars.md) | Templar Vows; Heirs of Sigismund; Space Marine Chapters | 100 / 18 | 22 |
| [Blood Angels](factions/guides/blood-angels.md) | Oath of Moment; The Sons of Sanguinius; Space Marine Chapters | 97 / 15 | 24 |
| [Blood Legions](factions/guides/blood-legions.md) | Pact of Blood; Blessings of Khorne | 30 / 5 | 8 |
| [Chaos Daemons](factions/guides/chaos-daemons.md) | The Shadow of Chaos; Daemonic Pact | 53 / 53 | 9 |
| [Chaos Knights](factions/guides/chaos-knights.md) | Harbingers of Dread; Super-heavy Walker; Dreadblades | 11 / 11 | 8 |
| [Chaos Space Marines](factions/guides/chaos-space-marines.md) | Dark Pacts; Cults of the Dark Gods | 54 / 54 | 17 |
| [Dark Angels](factions/guides/dark-angels.md) | Oath of Moment; The Unforgiven; The Ravenwing; The Deathwing; Space Marine Chapters | 98 / 16 | 24 |
| [Death Guard](factions/guides/death-guard.md) | Nurgle’s Gift (Aura); Pact of Decay | 30 / 30 | 8 |
| [Deathwatch](factions/guides/deathwatch.md) | Kill Teams; Oath of Moment; Space Marine Chapters | 92 / 10 | 17 |
| [Drukhari](factions/guides/drukhari.md) | Power From Pain; Corsairs and Travelling Players | 23 / 23 | 9 |
| [Emperor’s Children](factions/guides/emperors-children.md) | Thrill Seekers; Pact of Excess | 18 / 18 | 9 |
| [Genestealer Cults](factions/guides/genestealer-cults.md) | Cult Ambush | 24 / 24 | 9 |
| [Grey Knights](factions/guides/grey-knights.md) | Gate of Infinity | 25 / 25 | 9 |
| [Harlequins](factions/guides/harlequins.md) | Battle Focus; Disparate Paths | 63 / 8 | 14 |
| [Imperial Agents](factions/guides/imperial-agents.md) | Assigned Agents | 29 / 29 | 5 |
| [Imperial Fists](factions/guides/imperial-fists.md) | Oath of Moment; Space Marine Chapters | 85 / 3 | 17 |
| [Imperial Knights](factions/guides/imperial-knights.md) | Code Chivalric; Bondsman; Super-heavy Walker; Freeblades | 14 / 14 | 8 |
| [Iron Hands](factions/guides/iron-hands.md) | Oath of Moment; Space Marine Chapters | 84 / 2 | 17 |
| [Leagues of Votann](factions/guides/leagues-of-votann.md) | Prioritised Efficiency | 22 / 22 | 10 |
| [Legions of Excess](factions/guides/legions-of-excess.md) | Thrill Seekers; Pact of Excess | 23 / 5 | 10 |
| [Necrons](factions/guides/necrons.md) | Reanimation Protocols | 51 / 51 | 12 |
| [Orks](factions/guides/orks.md) | Waaagh!; Da Boss; Unstable energies; Special Move Types | 53 / 53 | 15 |
| [Plague Legions](factions/guides/plague-legions.md) | Nurgle’s Gift (Aura); Pact of Decay | 36 / 6 | 9 |
| [Raven Guard](factions/guides/raven-guard.md) | Oath of Moment; Space Marine Chapters | 84 / 2 | 17 |
| [Salamanders](factions/guides/salamanders.md) | Oath of Moment; Space Marine Chapters | 84 / 2 | 17 |
| [Scintillating Legions](factions/guides/scintillating-legions.md) | Cabal of Sorcerers; Pact of Sorcery | 34 / 6 | 9 |
| [Space Marines](factions/guides/space-marines.md) | Oath of Moment; Space Marine Chapters | 82 / 82 | 16 |
| [Space Wolves](factions/guides/space-wolves.md) | Oath of Moment; Curse of the Wulfen; Sagas; Sons of Russ; Space Marine Chapters | 103 / 21 | 23 |
| [Thousand Sons](factions/guides/thousand-sons.md) | Cabal of Sorcerers; Pact of Sorcery | 28 / 28 | 8 |
| [Tyranids](factions/guides/tyranids.md) | Synapse; Shadow in the Warp | 50 / 50 | 10 |
| [T’au Empire](factions/guides/tau-empire.md) | Drones; For the Greater Good | 40 / 40 | 7 |
| [Ultramarines](factions/guides/ultramarines.md) | Oath of Moment; Space Marine Chapters | 90 / 8 | 18 |
| [White Scars](factions/guides/white-scars.md) | Oath of Moment; Space Marine Chapters | 84 / 2 | 17 |
| [World Eaters](factions/guides/world-eaters.md) | Blessings of Khorne | 25 / 25 | 7 |
| [Ynnari](factions/guides/ynnari.md) | Battle Focus; Disparate Paths | 66 / 11 | 15 |

## What to work on first?

1. **Correct stale claims:** reconcile Acts of Faith turn timing, the Orks v946 refresh, changed costs/attachments, and conflicting coverage labels.
2. **Establish exact identities and source evidence:** resolve shared/variant ownership, retired entries and the source-scope hold before adding missing content.
3. **Close each field and rule gate:** use the linked unit/detachment audit and F02–F07 workstreams.
4. **Prove usable rosters:** complete adapter, replay, invalid-input and full-game coverage before upgrading status.

The [roadmap findings and sequence](FACTION_RULES_REMEDIATION_ROADMAP.md#initial-findings) give concrete evidence and acceptance criteria. This PR is documentation only; it changes no engine behavior, catalogs, pricing or geometry.

## Document layout

| Document | Purpose |
| --- | --- |
| `docs/factions/guides/<faction>.md` | Readable status, army rules, detachment overview, all unit costs and next work |
| `docs/factions/audit/<faction>.md` | Expandable named Enhancement/Stratagem inventories and unit field checklists with source links/fingerprints |
| `docs/factions/<faction>.md` | Existing generated historical coverage evidence; preserved under its generator contract |
| [Faction Rules Remediation Roadmap](FACTION_RULES_REMEDIATION_ROADMAP.md) | Findings, evidence gates, dependencies and ordered implementation work |
| [Faction Audit Sources](FACTION_AUDIT_SOURCES.md) | Observed versions, scope, counting and reconciliation method, pinned repository artifacts |
| [Track T taxonomy](factions/taxonomy/README.md) | Pre-gate semantic surveys; T1 Stratagem WHEN taxonomy, T2 effect taxonomy, T3 bearer/target/condition grammar, T4 army-construction grammar and T5 resource and state-token taxonomy are delivered |

Do not hand-edit the older generated reports to change a support claim. Fix the owning source/execution evidence and regenerate them in the corresponding implementation PR. Keep the readable guide synchronized with the evidence actually established.
