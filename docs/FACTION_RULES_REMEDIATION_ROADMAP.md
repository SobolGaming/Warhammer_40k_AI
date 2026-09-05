# CORE V2 Faction Rules Remediation Roadmap

[Faction guides and points](FACTION_SUPPORT.md) · [Observation register](FACTION_AUDIT_SOURCES.md) · [Core Rules roadmap](CORE_RULES_REMEDIATION_ROADMAP.md)

## Scope and audit result

This is the faction companion to the Core Rules roadmap. It inventories the
current in-scope 11th Edition faction views, army rules, detachments, and unit
datasheets observed on **5 September 2026**, then identifies the work needed to
certify their implementation. Repository evidence is pinned to **`52673fa1`**.
The latest version shown by the [40k.app faction update feed](https://www.40k.app/factions/updates)
was **946, released 2 September 2026**.

The inventory covers **40 faction/chapter/related-army views**, **982 distinct
datasheet source URLs**, and **506 distinct detachment source URLs**. The guides
contain 2,095 unit listing references because factions share entries. The
detachment pages contain 1,756 Enhancement/Upgrade entries and 2,520 Stratagem
entries, including inherited repetitions. These are source-navigation counts,
not distinct rules, supported units, or independent engine factions.

This PR completes the source inventory, field checklists, baseline report
comparison, and initial drift findings. It does **not** complete a clause-by-clause
runtime audit of all those rules. Every current-source certification remains
open. A checklist row is an obligation, not a claim that its behavior was tested.

The scope exclusions in [AGENTS.md](../AGENTS.md) continue to apply. Forge World,
Crusade, Boarding Actions, Kill Team as a separate game, and Legends content are
not admitted as supported rows. Current matched-play Deathwatch units named
“Kill Team” remain ordinary 40,000 datasheets. Titan faction views are excluded.
The [scope method and unresolved identity hold](FACTION_AUDIT_SOURCES.md#scope-and-identity)
must be read before treating this inventory as exhaustive beyond the admitted
scope. No runtime/catalog scope is expanded by this document.

## How to read the documentation

Start with [Faction support](FACTION_SUPPORT.md), choose a faction guide, and
expand an individual detachment or unit in its linked audit only when needed.
Each guide uses the same structure: current support limits, army rules, changes,
detachments, datasheets with all displayed points, and remaining work.

The older `docs/factions/<faction>.md` files remain generated evidence reports.
Their exact output is checked by repository tests. They are preserved for
traceability; the new guides are the human entry point. Changing their generators
and output contracts is a separate implementation task, not part of this
documentation-only PR.

## Status and acceptance gates

Status belongs to a **specific source version, selected content, and tested
consumer path**. Do not label an entire faction playable because its army-rule
module loads or one unit can shoot.

| Gate | Required evidence before the label is allowed |
| --- | --- |
| Source recorded | Approved complete operative source, provider and URL, version/date, transcription hash, observation fingerprint, stable source IDs, scope classification |
| Load supported | Typed catalog/source package loads eagerly with validated IDs, relationships, hashes, and provenance; no placeholder fields |
| Execution supported | Every relevant clause maps to RuleIR, a generic service/hook, or a justified named subsystem; the real lifecycle consumes it and records effects |
| Fieldable | A specified roster passes current points, DP, force disposition, composition, equipment, attachment, allies, uniqueness, and geometry validation through the engine |
| Playable | That fieldable roster can resolve all its selected rules and mandatory interactions through ordinary engine decisions without an unsupported path |
| Replay verified | The same decisions reproduce state/events; restore, serialization, hidden information, and adapter projections preserve the contract |
| Full support certified | All legal variants and rule branches in the declared scope/version have the preceding evidence, including invalid cases and cross-faction interactions |

`E` in the guides means the **baseline execution report classifies a matched
row as executable**. `Source` means the row exists without that classification;
`Missing` means no matching row was found. These labels describe reconciliation
candidates, not current approvals. The detailed tables separately preserve the
source report's `runtime_support_status`; the two reports can disagree.
No name-based candidate match transfers execution or identity to another faction.

The generated component report contains **59 datasheet rows across seven
factions**: Aeldari 29, Emperor's Children 13, Chaos Daemons 10, Chaos Space
Marines 2, Thousand Sons 2, World Eaters 2, and Death Guard 1. Its legacy overall
labels are **56 `Playable`, 3 `Blocked`, and 0 `Full`**. Those labels summarize
component coverage; they do not establish the current roster-level gates above.
Absence of a component row does not prove every reusable engine primitive is
missing. See the [pinned baseline artifacts](FACTION_AUDIT_SOURCES.md#repository-evidence).

The runtime module report separately records 28 faction modules: 23 partial,
5 placeholders, and none implemented; its 266 detachment modules comprise
8 implemented, 46 partial, and 212 placeholders. The 2,073 source coverage rows
classify 133 as executable generic IR and 23 as executable named handlers,
with 1,889 blocked for structured semantics and 28 blocked for source gaps.
These are different denominators and must not be combined into a coverage percentage.

## Initial findings

Priority 1 protects existing execution or roster claims from known drift.
Priority 2 closes inventory, evidence, and missing-content obligations. Findings
remain open until a source-backed implementation PR records its acceptance evidence.

| ID | Priority | Finding and consequence | Owning work |
| --- | --- | --- | --- |
| F-SOURCE-01 | 1 | The approved maintained-mirror policy explicitly covers Core Rules categories 01–25. It does not yet provide a faction-package ingestion contract. Browser observations in this audit are planning evidence. | F00 |
| F-ARMY-01 | 1 | Current Acts of Faith grants a Miracle die at each turn start. The Sororitas consumer and regression use battle-round start, so the implemented trigger is stale. | F02 |
| F-ORK-01 | 1 | v946 refreshes the Ork army and detachment roster. More Dakka! is removed in the update feed but remains an implemented module in the baseline report. Old eligibility and semantic claims need retirement/replacement review. | F01–F03 |
| F-DATA-01 | 1 | Current costs and attachments differ from older records. Eldrad's v931 cost is 120 points and its Leader recipient list changed. Bloodcrushers' six-model cost and third-unit surcharge differ from July values. | F01, F04, F07 |
| F-EVID-01 | 1 | Module status, source labels, execution classifications, and component `Playable` labels describe different facts. Some executable generic-IR rows retain `source_only` labels and no explicit consumer IDs. They need traceable consumer evidence before a playability claim. | F01, F08–F09 |
| F-OWN-01 | 2 | Shared source URLs, same-name faction variants, chapters, and related daemon views are not interchangeable identities. A flat name join would overstate coverage and can assign the wrong army ability. | F01, F04, F07 |
| F-GEOM-01 | 2 | No model-height field is exposed on the inspected App datasheets; 17 admitted source pages also lack a base field. Existing geometry statuses cannot certify unreviewed variants. | F06 |
| F-CORE-01 | 2 | Faction updates repeat shared Core Ability wording, including transport/destruction interactions. Those obligations belong to the common engine owner and the Core Rules roadmap. | F05–F08 plus Core Rules dependencies |
| F-DOC-01 | 2 | Dense generated faction reports mix evidence layers. Consistent guides and expandable inventories now separate them; automatic maintenance and certified status generation remain follow-up work. | F09 |
| F-SCOPE-01 | 2 | A current listing can reuse the name of historically excluded content. Warbuggies is held pending exact current-source identity review; its old Legends classification must neither admit nor conclusively classify the current entry by name alone. | F00–F01 |

### Evidence for the urgent findings

**Acts of Faith.** Compare the [current army rule](https://www.40k.app/factions/adepta-sororitas/army-rules)
with the `BATTLE_ROUND_START_TRIGGER` registration and resolver in
[the army-rule consumer](../src/warhammer40k_core/engine/faction_content/warhammer_40000_11th/adepta_sororitas/army_rule.py)
and `test_battle_round_start_gains_miracle_die_once_for_adepta_army` in
[its regression tests](../tests/unit/test_phase17g_adepta_sororitas_army_rule.py).
Closure must demonstrate both players' turn starts, duplicate-trigger prevention,
other gain sources, spending decisions, restore, and replay. It must not merely
change a constant while leaving an unconsumed subscription.

**Orks.** The [v946 update view](https://www.40k.app/factions/orks/updates)
lists 73 unit changes and 20 detachment changes before scope filtering.
The admitted [current detachment inventory](factions/guides/orks.md#detachments)
contains 15 entries. Compare current Waaagh!, Da Boss, psychic-resource rules,
and special movement clauses against the [baseline consumer](../src/warhammer40k_core/engine/faction_content/warhammer_40000_11th/orks/army_rule.py).
More Dakka! is a concrete stale selection claim; a renamed replacement does not
inherit its execution status. Removed datasheets must also leave the current
eligibility set. Do not scaffold excluded replacement/retired content.

**Costs and attachment permissions.** The
[Eldrad update](https://www.40k.app/931/factions/aeldari/units/eldrad-ulthran/updates)
changes 130 to 120 points and narrows the displayed Leader list to Guardian
Defenders and Storm Guardians. The
[Bloodcrushers update](https://www.40k.app/931/factions/chaos-daemons/units/bloodcrushers/updates)
changes six models from 190 to 200 points and the third-unit surcharge from
20 to 40. These are source-drift observations; the exact catalog IDs and
runtime application still need F01/F04 review. The current
[Exorcist](https://www.40k.app/factions/adepta-sororitas/units/exorcist)
also illustrates why a single points integer is insufficient: 180 points plus
40 for the second and subsequent copies. Equipment charges must be counted
per source-defined model/weapon, not dropped when parsing a minimum cost.

## Every datasheet's closure checklist

Every admitted datasheet has a linked field table under `docs/factions/audit/`.
It records all displayed cost rows, composition and characteristic profiles,
weapon/profile names, option-section presence, bases, keywords, attachment
recipients, and ability names. Full option prose and operative rule text remain
at the source link pending approved artifact retention in F00.

| Surface | What must be reconciled and tested | Owner |
| --- | --- | --- |
| Points | All model-count tiers, repeated-unit surcharges, equipment charges, included companion models, rounding/counting rules and current version | F04 |
| Composition and characteristics | Every model role/count, mixed profile, M/T/SV/W/LD/OC, damaged profile, unique model and legal size | F04/F07 |
| Wargear and weapon profiles | Default per-model ownership; all ranged/melee modes and characteristics; keywords, linked modes, multiple copies, equipment abilities | F05 |
| Wargear options | Replacements, mutually exclusive choices, per-N-model limits, leader-specific options, dependencies and illegal combinations | F05 |
| Base and height | Exact shape/dimensions, hull treatment, model-volume/height measurement, accepted variants and provenance; no zero/default geometry | F06 |
| Keywords | Canonical faction/unit/model tokens, conditional grants/removals, destroyed-model effects and attached-unit membership | F07 |
| Leadership / Support | Numeric LD plus Leader/Support slots, exact recipient IDs, attachment exceptions, attach/detach/destruction behavior | F04/F07 |
| Core abilities | Every instance and parameter, correct common consumer, timing/stacking/eligibility, current Core Rules dependencies | F07 |
| Unit and faction abilities | Every clause, optional choice, resource, trigger, target, duration, modifier, restoration and cross-rule interaction | F02/F07 |
| Other sections | Transport capacity and restrictions, orders, reserves/setup, damaged behavior, special army-construction and mission effects | F04–F08 |
| Operational proof | Legal/illegal roster validation, lifecycle loading, facade submissions, deterministic state/events, viewer-safe projections and replay | F08/F09 |

Absence of a field means **unresolved** or **not applicable with source evidence**,
never an invented default. Sir Hekhtur has no standalone cost displayed; his
inclusion relationship must be represented instead of assigning zero points.
Model height requires an accepted geometry source beyond the App page.

## Ordered implementation roadmap

The rows below are workstreams, not instructions to implement a whole faction
in one large PR. Open one bounded remediation PR at a time, complete its
acceptance evidence, review and merge it before the next. This documentation PR
does not start runtime implementation. Follow the repository's bottom-up order
and use the existing Core Rules roadmap for shared prerequisites.

| Order | Workstream and owning abstraction | Small complete deliverable | Acceptance evidence |
| --- | --- | --- | --- |
| F00 | Faction source governance: source-package policy and validators | Extend the maintained-App evidence contract to in-scope faction, detachment and datasheet packages; define geometry authority and selected version | Complete retained observations with stable IDs, hashes and provenance; divergence/ambiguity and excluded-content validation; no live runtime fetches |
| F01 | Inventory, source identity and evidence reconciliation: catalog/source manifests and coverage reports | Build explicit provider-to-catalog crosswalks; reconcile v946/v931/v925/v913 and any older delta required by each source's baseline; record added, changed, removed, shared and unresolved content | No duplicate identity transfer or omitted admitted URL; report each existing executable row as revalidated, stale, retired or unresolved; track partial clauses and evidence layers separately |
| F02 | Army rules: faction orchestrators plus existing generic services | Correct F-ARMY-01 and review the Ork refresh first; then close each army rule and allied/related-army restrictions in dependency order | Real resource/phase/choice lifecycle tests; current source clauses, duplicate/stale trigger rejection, restore and deterministic replay; bespoke-handler justification where required |
| F03 | Detachments: army construction, RuleIR, Enhancements and Stratagem services | Reconcile every DP/force-disposition entry; implement rule families including Upgrades, bearer/keyword restrictions, costs and all named subrules | Source IDs for every rule; legal/illegal detachment and bearer selection; CP/once-per-window rules; real lifecycle execution and adapter decisions |
| F04 | Datasheet pricing and mustering: catalog, points, roster and attachment validators | Current complete costs, compositions, model roles and related/ally eligibility; resolve inclusion-only entries and retired choices | Boundary tests for every cost tier/surcharge and composition family; mixed-roster validation; no legal configuration admitted with missing required data |
| F05 | Equipment: typed wargear/profile catalogs and attack services | Exact profile variants, default loadouts and option constraints; reuse generic weapon/equipment semantics | Valid and invalid per-model loadouts, multiple weapon instances, mode choice, profile keywords, ownership and attack-path regressions |
| F06 | Geometry: model-volume catalog, model groups, visibility and pathing | Source-backed base/hull/height records for all accepted model variants, including mixed-model units | No missing geometry for a fieldable roster; group-aware coherency, range/visibility, collision, transport and movement witnesses |
| F07 | Datasheet semantics: descriptors, attachment groups, common ability/hook owners | Exact keywords, Leadership/Support, Core/Unit abilities and additional sections for each unit; reuse F02/F05 services | One clause-to-consumer map per source rule; attached-unit, destroyed-model, timing/stacking and negative cases; no display-name runtime gates |
| F08 | End-to-end operation: lifecycle, adapters and replay | Certify selected representative rosters, then expand to every legal variant and cross-faction interaction | AdapterGameSession/LocalGameSession submissions, deterministic finite IDs/proposals, rejected inputs, viewer redaction, restore and full-game replay |
| F09 | Coverage certification and documentation: evidence generator and readable guides | Generate separated source/load/execution/fieldability/playability/replay evidence and keep the human guides concise | Fresh audit of all admitted URLs against one retained target snapshot; no open mandatory clause/field; generated checks and complete repository gates |

F01 depends on F00 for implementation-ready source packages. F02–F07 depend on
their exact source identities and existing common engine prerequisites; a later
workstream can supply a prerequisite for an earlier faction-specific slice.
F08 depends on all selected content's field and rule gates. F09 depends on F08
and closure of every in-scope obligation, not a percentage threshold.

Within F03/F05/F07, group reusable work by semantics: attack modifiers and
rerolls; ability grants; resource/CP accounting; movement/reserve/setup hooks;
restoration/destruction; objective control; targeting/eligibility; attachment
and roster restrictions. Add a generic hook only for a real source-backed
consumer in the same PR. Reuse engine-owned mutation and decisions. Named
handlers remain exceptions for bespoke faction state/resources/orchestration
under [AGENTS.md](../AGENTS.md), with budget and lifecycle evidence.

Do not close a faction row while a selected Core Ability depends on an open
[Core Rules finding](CORE_RULES_REMEDIATION_ROADMAP.md). Transport destruction,
disembark, movement paths, Hazardous weapon instances, attached groups, and
damage allocation need their shared owners' evidence. Copying a local faction
implementation would create divergent rules paths.

After integration with `main` at `94972c20`, Order 18/P14 supplies the shared
objective-geometry query and explicit source `objective_scope` classification.
New faction source ingestion and objective effects must reuse those owners.
Faction-specific effects such as the Chaos Daemons corrupted-realspace aura
still require their own source and consumer review; the merged Core Rules work
does not close those F07 obligations.

## Evidence required to close an implementation slice

Record the source version, faction/detachment/datasheet IDs, exact clauses,
descriptor/execution IDs, owning consumers, remaining unsupported branches,
test references, and generated artifact hashes. State which acceptance gates
actually passed. Update the relevant guide and audit; preserve history when a
new source invalidates a previously certified claim.

Use focused regressions while iterating, then the current repository's complete
PR gates after scope and architecture review. Tests must use real domain
objects and the shared decision path. A docs checkbox, loaded placeholder,
mocked handler, or successful parser is not execution evidence.

## Re-audit policy

For content with execution evidence, start at the
[faction update feed](https://www.40k.app/factions/updates), follow the applicable
version and changed-item pages, and compare complete current clauses with the
retained implementation source. Inspect removals as well as modifications.
No update entry is not proof of equivalence when the repository baseline is older.

For missing content, start at the [faction directory](https://www.40k.app/factions)
and enumerate its current army-rule, detachment and unit navigation. Preserve
related-army ownership and shared links. Resolve scope and source completeness
before adding catalog/runtime rows. Reconcile points and geometry independently
of ability execution.

A later App update reopens affected source and gameplay gates. F09 must record
the actual selected version and audit date; this 5 September inventory must not
be described as indefinitely current.
