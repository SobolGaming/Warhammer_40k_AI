# CORE V2 Faction Rules Roadmap

[Faction guides and points](FACTION_SUPPORT.md) · [Observation register](FACTION_AUDIT_SOURCES.md) · [Source policy (F00)](FACTION_RULES_SOURCE_POLICY.md) · [Core Rules roadmap](CORE_RULES_REMEDIATION_ROADMAP.md)

## Purpose and decisions

This document replaces the September 2026 remediation roadmap (F00–F09) with a
complete plan for bringing every in-scope Warhammer 40,000 11th Edition faction,
detachment, Enhancement, Upgrade, Stratagem and datasheet to certified full
support, and for keeping that support current across App-data releases,
including faction rewrites. F00 is complete and its evidence is preserved
below. F01–F09 are superseded; a [legacy ID map](#legacy-workstream-ids) keeps
the existing guides and audits readable.

Owner decisions recorded on 9 September 2026:

| # | Decision | Consequence |
| --- | --- | --- |
| D1 | 40k.app is the single current authority for both structured datasheet/detachment data and operative rule text. | Catalog generation and every Wahapedia-fed generator migrate to a versioned content set extracted from retained 40k.app pages. The Wahapedia snapshot is frozen as a legacy identity crosswalk. Official GW PDFs remain official provenance. |
| D2 | The Orks update pilot runs in parallel with the Chaos Daemons slice. | FM0.5 exercises the diff, classification, retirement and status-invalidation tooling on the two most recent Orks versions while FM1-a implements Chaos Daemons. |
| D3 | Content-set retention is current plus one previous version, applied per faction and only after that faction's first full-support certification. | Before a faction's -b certification milestone closes, only the current version of its content is packaged. From that event onward, its previous version is also packaged, every handler it needs is retained, and its replays are covered by the U7a replay compatibility contract; retention without U7a coverage is reported as `exact_build_only`, not as replayability. |
| D4, D7 | All Core Rules orders close before faction implementation begins. | "Playable" has no Core-exception list. Army-construction facts (DP budgets, force-disposition consistency, Enhancement-only detachments) are settled by Core P25A–C. |
| D5 | Space Marines are a super-family: the shared detachments are certified once, chapter views are overlays. | S2 models detachment identity as owned by the Space Marines view with chapter overlay records for chapter-owned rules, detachments and eligibility. Grey Knights is outside the overlay. |
| D6 | Content is JSON records with typed loaders; no per-detachment Python unless a named handler is justified. | The Python scaffold, its generator and the placeholder modules are removed in FM0. Existing implemented Python detachment modules migrate to data bindings as each generic family lands. Python required by any packaged content-set version is retained until no packaged version references it. |
| D8 | Documentation-only work may run in parallel with the remaining Core Rules orders. | The [pre-gate documentation track](#fm-pre-documentation-only-work-permitted-before-gate-0) lists exactly what may proceed before Gate 0. |

## Scope

The scope exclusions in [AGENTS.md](../AGENTS.md) apply unchanged. Forge World,
Crusade, Boarding Actions, Kill Team as a separate game, and Legends content are
not admitted. Titan Legions and Chaos Titan Legions are excluded. Current
matched-play Deathwatch datasheets named "Kill Team" are ordinary datasheets.

The admitted corpus is the 40k.app faction directory: 36 primary faction views
(7 Imperium, 13 Space Marines, 8 Chaos, 8 Xenos), 34 of them in scope after the
Titan exclusions, plus 6 related-army views (Harlequins, Ynnari, Blood Legions,
Plague Legions, Legions of Excess, Scintillating Legions), for the 40 admitted
views inventoried on 5 September 2026 at App-data 946: 982 distinct datasheet
URLs, 506 detachment URLs, 1,756 Enhancement/Upgrade entries and 2,520 Stratagem
entries including inherited repeats. After identity resolution the distinct
denominators are expected near 270–300 detachments, 1,000 Enhancements/Upgrades
and 1,400 Stratagems; S2 records the exact figures. The [observation
register](FACTION_AUDIT_SOURCES.md) and [scope method](FACTION_AUDIT_SOURCES.md#scope-and-identity)
remain the record of that inventory. Every later milestone re-observes the
corpus at the then-current App-data version; the September counts are not
indefinitely current.

## Method: breadth-first inventory and taxonomy, depth-first certification

Pure depth-first work (finish one faction, then the next) lets the first
consumer shape each abstraction; the content-specific branches that already
exist in `engine/army_mustering.py` for Shadow Legion, Corsair Coterie and
Be'lakor are the result. Pure breadth-first work (implement each semantic
family across all factions before certifying any roster) delays every playable
faction and never exercises the full-game and replay paths where defects
surface. The roadmap therefore runs three loops:

1. **Breadth loop, data only.** Retain every admitted page at one pinned
   App-data version, resolve identities, extract structure, and classify every
   rule clause into a semantic taxonomy. The output is the **semantic demand
   matrix**: rows are semantic families, timing windows and decision kinds;
   columns are factions; cells count the army rules, detachment rules,
   Enhancements, Stratagems and datasheet abilities that need them. No engine
   semantics are written in this loop.
2. **Depth loop, one priority faction at a time.** Certify a faction as a
   vertical slice to full-game replay. Each generic family the slice needs is
   designed against the demand matrix for every faction that needs it, with one
   consumer from the priority faction and one regression from a non-priority
   faction proving content neutrality.
3. **Saturation loop.** Later factions become mostly data bound to existing
   families. Progress is measured as rules unlocked per family and the share of
   new content that needs Python; a rising code share stops the wave for family
   redesign.

Family selection rule: implement next the family that unlocks the most rules in
the current priority faction, provided at least two factions demand it or a
documented bespoke-subsystem justification exists under the named-handler
policy in [AGENTS.md](../AGENTS.md).

Design rules enforced by code-quality tests (Q2):

1. Content is data; code is generic. A new detachment, Enhancement, Stratagem or
   datasheet ability adds JSON records and no Python unless it needs a new
   generic family.
2. Generic surfaces are specified from the corpus demand matrix, never from the
   first consumer.
3. Every new family ships with at least two consumers from two factions, or the
   list of corpus rules it will serve plus a non-priority regression.
4. Identity is stable source IDs. Display names, normalized text tokens and
   locally re-normalized keywords never gate behaviour.
5. No source version appears in module or package names; versions live in
   content-set identifiers.
6. Retirement is first class. Every content record can carry `retired_in` and
   `superseded_by`; mustering at or after `retired_in` rejects the ID with a
   typed reason, while games and replays declaring an earlier packaged version
   still execute it. Rejection from current-version mustering and availability
   for historical replay are different facts and are reported separately.
7. One denominator model for status; one generated status artifact feeds every
   document and the capability manifest.

<a id="status-and-acceptance-gates"></a>
## Content model and status ladder

Entities, each with a stable project-owned ID, a crosswalk row and a status
record: faction view; army rule and its clauses; related-army pact (Daemonic
Pact, Pact of Blood/Decay/Excess/Sorcery, Disparate Paths, Space Marine
Chapters, Assigned Agents, Corsairs and Travelling Players, Brood Brothers,
auxiliary rules); detachment (rule clauses, DP, force disposition,
Enhancements/Upgrades with bearer grammar, Stratagems); datasheet (model
profiles, composition tiers, every cost row including repeated-unit surcharges
and equipment charges, wargear and options, keywords, Leader/Support, Core and
unit abilities, transport and damaged sections, geometry per model variant);
content set (one App-data version of the admitted corpus with official
provenance links, crosswalk and tombstones).

| Level | Name | Evidence required |
| --- | --- | --- |
| — | Staging | Observation without registered official provenance, held outside the admitted package as `blocked_provenance`; planning evidence only, never packaged, never counted toward any level |
| L0 | Observed | Retained page under the F00 contract: hashes, App-data version, resolved identity, scope class, registered official provenance |
| L1 | Loaded | Typed content-set record accepted by the fail-fast loader; crosswalk row present |
| L2 | Structured | Datasheet: every cost tier, composition, option, keyword, Leader/Support. Detachment: DP, force disposition, complete Enhancement/Stratagem inventories with costs and bearer text |
| L3 | Geometry | Accepted base/hull/height evidence for every model variant (datasheets only) |
| L4 | Mapped | Every clause maps to a RuleIR template, a generic family, a justified named handler, or a typed `unsupported` reason; demand matrix updated |
| L5 | Executable | Real lifecycle consumer exercised with real domain objects; deterministic replay payloads; unsupported branches typed |
| L6 | Fieldable | At least one roster accepted by mustering and one illegal variant rejected with a typed reason |
| L7 | Playable | At least one headless full game through `AdapterGameSession`/`LocalGameSession` with exact replay reproduction, viewer-scoped projections and zero unsupported diagnostics |
| L8 | Certified | All variants, branches, negative cases and cross-faction interactions covered at the pinned version |

Freshness is orthogonal: `current`, `stale` (source drift since the evidence was
recorded) or `retired`. A faction is fully supported at version V only when
every non-retired entity it owns or inherits is L8 and `current` at V. Reports
show counts per level and freshness; no single percentage is published.

Decomposition used for the L4–L5 gates:

- A **Stratagem** has four coordinates: timing window (engine
  `TimingTriggerKind`, reaction or opportunity window), target grammar, effect
  template (RuleIR bound to a generic handler) and restriction grammar (CP,
  once-per-phase/battle, keywords, conditions). It is *usable* when it appears
  as a `use_stratagem` option at its window with correct targets and CP, and
  *executable* when its effect applies through an engine-owned path. A missing
  coordinate is a Track G backlog item counted across the corpus.
- An **Enhancement or Upgrade** has bearer grammar ("Warboss model only",
  "Infantry Warboss model only", unit-wide Upgrade), effect template and use
  ledgers.
- A **detachment rule** has condition (state token, keyword, phase), effect
  template and army-construction constraints (Keywords sections, required or
  prohibited units and detachments, DP, disposition).
- A **datasheet ability** is certified per unit but implemented per semantic
  family across the faction; datasheet work is grouped by family, not by unit.

<a id="initial-findings"></a>
## Open findings

Findings remain open until a source-backed implementation records acceptance
evidence. Owning work now references tracks and milestones.

| ID | Priority | Finding and consequence | Owning work |
| --- | --- | --- | --- |
| F-ARMY-01 | 1 | Current Acts of Faith grants a Miracle die at each turn start; the Sororitas consumer and regression use battle-round start. | Debt item 9 in FM0; first case for the "IR changed → consumer stale" rule (U4) |
| F-ORK-01 | 1 | v946 refreshes the Ork army and detachment roster: seven detachments added, More Dakka! removed, DP costs and Enhancement/Stratagem inventories changed, 73 unit changes. Retired scaffold directories remain. | FM0.5 pilot; U5–U6 |
| F-DATA-01 | 1 | Current costs and attachments differ from older records (Eldrad, Bloodcrushers, Exorcist surcharge). | S3a; impact class "points only" and "attachment change" in U3; FM1 and FM3 |
| F-EVID-01 | 1 | Module status, source labels, execution classifications and component labels describe different facts with different denominators. | Q1 |
| F-OWN-01 | 2 | Shared URLs, same-name variants, chapters and related daemon views are not interchangeable identities. | S2 |
| F-GEOM-01 | 2 | No model-height field on App datasheets; 17 pages lack a base field. | S5 |
| F-CORE-01 | 2 | Shared Core Ability wording belongs to the common engine owner. | Gate 0 (Core roadmap PFINAL) |
| F-DOC-01 | 2 | Generated reports mix evidence layers; guides are hand-maintained. | Q1, D1 |
| F-SCOPE-01 | 2 | Warbuggies reuses the name of historically excluded content; held pending exact identity review. | S2 |
| F-DEBT-01 | 1 | Generic lifecycle code branches on faction/detachment IDs and a display name (`army_mustering.py`); the scaffold generator carries a hand-maintained implemented-ID map; per-detachment RuleIR and the detachment source table are Python modules; dated runtime modules encode a source version; only Death Guard has unit/wargear Python modules. | Debt items 1–8 in FM0 |

Evidence for F-ARMY-01, F-ORK-01 and F-DATA-01 is unchanged from the September
review: compare the [current Acts of Faith](https://www.40k.app/factions/adepta-sororitas/army-rules)
with `BATTLE_ROUND_START_TRIGGER` in
[the army-rule consumer](../src/warhammer40k_core/engine/faction_content/warhammer_40000_11th/adepta_sororitas/army_rule.py);
compare the [Orks v946 update view](https://www.40k.app/factions/orks/updates)
with the [baseline Waaagh! consumer](../src/warhammer40k_core/engine/faction_content/warhammer_40000_11th/orks/army_rule.py);
and see the [Eldrad](https://www.40k.app/931/factions/aeldari/units/eldrad-ulthran/updates),
[Bloodcrushers](https://www.40k.app/931/factions/chaos-daemons/units/bloodcrushers/updates)
and [Exorcist](https://www.40k.app/factions/adepta-sororitas/units/exorcist)
pages for cost and attachment drift.

## Every datasheet's closure checklist

Every admitted datasheet has a linked field table under `docs/factions/audit/`.
Absence of a field means unresolved or not applicable with source evidence,
never an invented default. Sir Hekhtur has no standalone cost; his inclusion
relationship is represented instead of zero points. Model height requires an
accepted geometry source beyond the App page.

| Surface | What must be reconciled and tested | Owner |
| --- | --- | --- |
| Points | All model-count tiers, repeated-unit surcharges, equipment charges, included companion models, current version | S3a, Track C |
| Composition and characteristics | Every model role/count, mixed profiles, M/T/SV/W/LD/OC, damaged profile, unique model, legal sizes | S3a, Track C |
| Wargear and weapon profiles | Default per-model ownership; all ranged/melee modes; keywords, linked modes, multiple copies, equipment abilities | S3a, Track G attack families |
| Wargear options | Replacements, exclusive choices, per-N-model limits, leader-specific options, dependencies | S3a, Track C |
| Base and height | Exact shape/dimensions, hull treatment, height, accepted variants and provenance | S5 |
| Keywords | Canonical tokens, conditional grants/removals, destroyed-model effects, attached-unit membership | S3a, Core P02D, Track G keyword family |
| Leadership / Support | LD plus Leader/Support slots, exact recipient IDs, attachment exceptions | S3a, Core P19, Track C |
| Core abilities | Every instance and parameter, correct common consumer, timing/stacking/eligibility | Gate 0 |
| Unit and faction abilities | Every clause, choice, resource, trigger, target, duration, modifier, restoration and interaction | T2, Track G, Track C |
| Other sections | Transport capacity and restrictions, orders, reserves/setup, damaged behaviour, army-construction and mission effects | Track C |
| Operational proof | Legal/illegal rosters, lifecycle loading, facade submissions, deterministic events, viewer-safe projections, replay | Q3, Q4, Track C |

## Tracks

Each item is one or a few bounded PRs opened one at a time, with acceptance
evidence recorded before the next starts.

### Track S: source and identity

| ID | Deliverable | Acceptance evidence |
| --- | --- | --- |
| S1 | Retain all 40 admitted views at V0 (the App-data version current at Gate 0) under the F00 contract. Amend the F00 policy to admit 40k.app versioned-path observations (`/<version>/factions/...`) for historical diff fixtures only; they never authorize a current content set. | Every admitted URL has a retained observation with fingerprint; excluded and held content rejected by validators; source-authority registry updated; policy amendment and validator coverage in the same PR |
| S2 | Identity: project-owned catalog ID registry (existing catalog IDs are grandfathered and become project-owned; new entities receive registry-allocated IDs, never name-derived), crosswalk to 40k.app page IDs, GW PDF rows and the frozen Wahapedia IDs; Space Marines inheritance/overlay model; related-army and shared-page ownership; Warbuggies and Sir Hekhtur resolved or listed unresolved | No name joins; slug renames are crosswalk updates, not identity changes; existing army lists and replay artifacts resolve unchanged |
| S3a | Structured extraction at the data boundary from retained pages into the content set: datasheets, detachments, army rules, pacts; typed fail-fast loader | Missing fields fail; every admitted record carries source ID, transcription hash and registered official provenance (non-empty `official_source_ids` resolving to retained official artifacts with hashes, exactly as the F00 validator requires today); an observation without registered official provenance is a **staging observation** (see below), never an admitted record; no runtime module parses page text |
| S3b | Dual-run catalog generation for currently supported content: Wahapedia rows versus content set, field-by-field diff | Every difference attributed to source drift or an extraction defect; nothing accepted silently |
| S3c | Switch `rules/catalog_generation.py` to the content set; freeze the Wahapedia snapshot as legacy crosswalk input only. Depends on U7a (replay compatibility contract) being merged first | Engine build identity and external contract regenerated; committed player army-list artifacts resolve their grandfathered catalog IDs unchanged; committed replay fixtures reproduce under the new build through the U7a mechanism, or are regenerated with a recorded justification per fixture; snapshot path label resolved |
| S3d | Re-point Wahapedia-fed generators (Stratagem activation support, keyword lexicon, RuleIR shard ownership); replace `faction_detachments_2026_27.py` and the per-detachment `*_ir_support_2026_27.py` modules with content-set records | No runtime module imports the snapshot or a dated detachment module |
| S4 | Version ledger and content-set diff tool at entity and field granularity, including removals | The Orks 931→946 fixture reproduces the update feed's 20 detachment and 73 unit changes |
| S5 | Geometry authority corpus: base/hull/height evidence per model variant for every datasheet, through the existing `ModelGeometrySourceEvidence` and `ModelGeometryCatalogRecord` owners | Missing evidence is `blocked`; fieldability consumes the record; no defaults |

Content-set layout (to be confirmed in S3a): `rules/source_packages/warhammer_40000_11th/app_content_sets/<app_data_version>/` containing `manifest.json`, `factions/`, `detachments/<faction>/`, `datasheets/<faction>/`, `crosswalk.json` and `tombstones.json`. Retained observations stay under `data/source_audits/maintained_app_mirrors/`. Packaged size is measured in S3a; compression is applied if the wheel budget requires it.

**Staging observations and official provenance.** The F00 contract requires
every retained observation to carry independent official historical source IDs,
retained artifact paths and hashes; the validator rejects a row whose official
references do not resolve. This roadmap does not weaken that contract. An
App page whose content has no registered official artifact yet (for example a
newly added datasheet before its faction-pack PDF is retained) is held as a
staging observation under `data/source_audits/staging/`: it may inform Track T
surveys, the demand matrix and task packets, but it is outside the admitted
package, cannot enter the authorized content set, cannot reach L0 in the status
ladder, and is reported with the distinct freshness/blocker value
`blocked_provenance`. Admission requires retaining the official artifact under
`data/raw/faction_packs` with its SHA-256 and registering it in the audit, in a
reviewed PR. If the owner ever wants App-only content admitted without an
official artifact, that is a separately reviewed F00 policy and validator
amendment with its own regression evidence; it is not scheduled by this roadmap
and a staging marker never becomes evidence by default. Q1 must preserve the
distinction between `blocked_provenance` staging observations and admitted
records in every generated report. Acceptance for S3a includes a fixture where a
pending-provenance observation is rejected from the content set while a
complete-provenance record is admitted.

### Track T: corpus taxonomy and semantic demand

| ID | Deliverable |
| --- | --- |
| T1 | Stratagem WHEN taxonomy over every distinct Stratagem: the closed window set and the gap list against the current 27 `TimingTriggerKind` values plus reaction and opportunity windows. **Delivered** read-only to Track G in [T1_STRATAGEM_WHEN_TAXONOMY.md](factions/taxonomy/T1_STRATAGEM_WHEN_TAXONOMY.md); the previous "26" count was stale |
| T2 | Effect taxonomy for abilities, Enhancements, Stratagems and detachment rules: RuleIR template catalogue with counts (hit/wound/save/damage modifiers, rerolls, weapon keyword and profile grants, Feel No Pain and damage reduction, invulnerable/save grants, movement permissions, redeploy/teleport, reserves changes, mortal wounds, fight-order changes, target restrictions, keyword grants, resource gain/spend, healing/revival/return, transport interactions, weapon grants, attachment changes, OC changes, CP gain/refund, Battle-shock manipulation). **Delivered** read-only to Track G in [T2_EFFECT_TAXONOMY.md](factions/taxonomy/T2_EFFECT_TAXONOMY.md) |
| T3 | Bearer, target and condition grammar, including state tokens such as "riled up" or "Waaagh! active", ranges, visibility, phase and turn ownership. **Delivered** read-only to Track G in [T3_BEARER_TARGET_CONDITION_GRAMMAR.md](factions/taxonomy/T3_BEARER_TARGET_CONDITION_GRAMMAR.md) |
| T4 | Army-construction grammar: DP budgets per battle size, multiple detachments per army, force-disposition consistency, duplicate-detachment prohibition, required and prohibited units and detachments, Enhancement counts, Enhancement-only detachments (Brute Bosses has six Enhancements and no Stratagems), related-army admission and caps, model-specific Warlord and bearer. **Delivered** read-only to Core P25C in [T4_ARMY_CONSTRUCTION_GRAMMAR.md](factions/taxonomy/T4_ARMY_CONSTRUCTION_GRAMMAR.md) before P25C is implemented |
| T5 | Resource and state-token taxonomy across all 28 army rules (Miracle dice, Pain, Blessings, Battle Focus, Waaagh!, Strands of Fate, Yield, Cabal, Doctrina, Dread, Oath, Vows, Ka'tah, Orders, Kill Teams, Cult Ambush, Reanimation, Synapse/Shadow, Greater Good, Gate of Infinity, Assigned Agents, Code Chivalric, Power from Pain, Thrill Seekers, Dark Pacts, Nurgle's Gift, Shadow of Chaos): which share a typed `ResourceLedger` service and which remain bespoke state machines under the named-handler budget. **Delivered** read-only to Track G in [T5_RESOURCE_STATE_TOKEN_TAXONOMY.md](factions/taxonomy/T5_RESOURCE_STATE_TOKEN_TAXONOMY.md) |
| T6 | Decision-kind and viewer-visibility demand: finite options versus parameterized proposals per rule family; adapter contract deltas. **Delivered** read-only to Track G in [T6_DECISION_KIND_VISIBILITY.md](factions/taxonomy/T6_DECISION_KIND_VISIBILITY.md) |

Output: `semantic_demand_matrix.json` plus a generated table, regenerated on
every content-set change. Pre-gate surveys are planning evidence; FM0
regenerates the matrix from the retained content set and reconciles it with
the surveys. T1's [`t1_when_windows.json`](factions/taxonomy/t1_when_windows.json),
T2's [`t2_effect_families.json`](factions/taxonomy/t2_effect_families.json),
T3's [`t3_bearer_target_conditions.json`](factions/taxonomy/t3_bearer_target_conditions.json),
T4's [`t4_constraint_families.json`](factions/taxonomy/t4_constraint_families.json),
T5's [`t5_resource_state_tokens.json`](factions/taxonomy/t5_resource_state_tokens.json),
and T6's [`t6_decision_kinds.json`](factions/taxonomy/t6_decision_kinds.json)
are planning evidence only and are not that matrix.

### Track G: generic engine families

Designed from Track T, implemented inside the depth loop. Each family delivers
a typed hook or RuleIR handler, the engine-owned consumer and mutation, the
adapter contract update, replay and restore coverage, one priority-faction
consumer, one non-priority regression, and flips its demand-matrix rows to
executable. Candidate families, to be confirmed and ordered by T1–T6: timing
windows and opponent reaction windows (T1 delivered the closed WHEN set and
gap list in [T1_STRATAGEM_WHEN_TAXONOMY.md](factions/taxonomy/T1_STRATAGEM_WHEN_TAXONOMY.md));
the EFFECT catalogue (T2 delivered the closed family set and gap list in
[T2_EFFECT_TAXONOMY.md](factions/taxonomy/T2_EFFECT_TAXONOMY.md));
bearer, target and condition grammar (T3 delivered the closed bearer, TARGET
clause and condition set in
[T3_BEARER_TARGET_CONDITION_GRAMMAR.md](factions/taxonomy/T3_BEARER_TARGET_CONDITION_GRAMMAR.md));
army-construction constraint
records on Core P25C surfaces (T4 delivered the grammar in
[T4_ARMY_CONSTRUCTION_GRAMMAR.md](factions/taxonomy/T4_ARMY_CONSTRUCTION_GRAMMAR.md));
shared resource ledgers (T5 delivered the closed token set and ledger-fit
split in
[T5_RESOURCE_STATE_TOKEN_TAXONOMY.md](factions/taxonomy/T5_RESOURCE_STATE_TOKEN_TAXONOMY.md));
decision-kind and viewer-visibility demand (T6 delivered the closed
submission and visibility axes and the adapter-contract delta list in
[T6_DECISION_KIND_VISIBILITY.md](factions/taxonomy/T6_DECISION_KIND_VISIBILITY.md)).
New families require a real source-backed consumer in the same PR; speculative
registries are forbidden.

### Track C: faction certification slices

Every slice follows the same order: army rule and pact → detachments (rule,
Enhancements, Stratagems, constraints) → datasheets grouped by semantic family
(pricing, composition, wargear, geometry, keywords, leaders, abilities) →
fieldability (legal and illegal rosters) → headless full games and replay →
generated guide refresh. Existing execution claims in a slice are revalidated
against V0 before any new work reuses them.

| Slice | Scope at App-data 946 (re-counted at V0) | Notes |
| --- | --- | --- |
| C-CD Chaos Daemons | 53 datasheets, 9 detachments; The Shadow of Chaos, Daemonic Pact | Owns shared identity for the Blood/Plague/Excess/Scintillating Legion views; five detachments with existing execution revalidated first; Bloodcrushers cost drift |
| C-EC Emperor's Children | 18 datasheets, 9 detachments; Thrill Seekers, Pact of Excess | Legions of Excess pact; two implemented detachments revalidated |
| C-AE Aeldari | 55 datasheets, 14 detachments; Battle Focus, Disparate Paths | Harlequins (8 owned datasheets) and Ynnari (11 owned) views; Eldrad cost and Leader drift; Strands of Fate resource |
| C-WE World Eaters | 25 datasheets, 7 detachments; Blessings of Khorne | Blood Legions pact; Khorne Daemonkin cross-faction eligibility |
| C-OR Orks | 53 datasheets, 15 detachments; Waaagh!, Da Boss, Unstable energies, Special Move Types | Follows the FM0.5 pilot; retired detachments already tombstoned |
| Wave 2: Chaos | Chaos Space Marines, Death Guard, Thousand Sons, Chaos Knights | Share Dark Pacts and daemon pacts; RuleIR shards exist for CSM and Thousand Sons |
| Wave 3: Space Marines super-family | Space Marines' shared detachments certified once; 12 chapter overlays (chapter-owned army rules such as Templar Vows, The Sons of Sanguinius, The Unforgiven, Curse of the Wulfen/Sagas; chapter-owned detachments: Black Templars 6, Blood Angels 8, Dark Angels 8, Space Wolves 7, Ultramarines 2, Deathwatch 1 plus Kill Teams, Imperial Fists/Iron Hands/Raven Guard/Salamanders/White Scars 1 each, subject to S2) | Grey Knights (Gate of Infinity, 9 own detachments) is certified separately |
| Wave 4: Imperium | Adepta Sororitas (F-ARMY-01 closed in FM0), Adeptus Custodes, Astra Militarum, Adeptus Mechanicus, Imperial Agents, Imperial Knights | |
| Wave 5: Xenos | Drukhari, Genestealer Cults, Leagues of Votann, Necrons, Tyranids, T'au Empire | |
| C-FINAL | Corpus-wide L8 audit at one pinned version | |

Wave order after FM5 is a proposal. By Wave 2 most work should be data only, so
waves may run as parallel agent packets under the data-first contract (D3).

### Track U: update pipeline

| ID | Deliverable |
| --- | --- |
| U1 | Offline capture tool: given a human-triggered snapshot of the update feed and changed pages, writes a staging audit for review. Never runtime input, consistent with F00 |
| U2 | Content-set diff (S4) between the packaged version and the staged version |
| U3 | Impact classifier producing impact classes and generated task packets in the data-first packet format |
| U4 | Automatic, layer-specific status invalidation (rules below): semantic execution, roster legality and certification claims are bound to separate evidence tuples; a changed transcription hash is provenance, not automatic semantic demotion, and requires impact classification plus a recorded carry-forward or a stale claim; unclassified changed clauses are `stale` pending review; CI fails if a guide asserts `current` for a stale row |
| U5 | Retirement and supersession records (`retired_in`, `superseded_by`) governing current-version mustering only: a roster built against a content-set version at or after `retired_in` is rejected with a typed reason, while a game or replay declaring an earlier packaged version still loads and executes the record. The content-set/Python parity check removes Python only when no packaged content-set version references it |
| U6 | Faction rewrite procedure: a new content-set version for the faction, full L0–L8 re-run with the same tooling, explicit retirement of every removed entity, guide regenerated |
| U7 | Retention and coexistence per D3: the current content set is always packaged; a faction's previous version is packaged only after that faction's first full-support certification. Game configuration and replay artifacts carry the engine build identity and the content-set version of every participating faction; loading a replay whose faction content is not packaged fails closed with a typed error naming the repository tag that has it |
| U7a | Replay compatibility contract (prerequisite of S3c and FM0 exit, owned jointly with the adapter/persistence contract owner): the mechanism below by which a retained previous content-set version remains replayable on a newer engine build without ignoring build identity; contract, conformance scenarios and regressions in the same PR |
| U8 | Runbook and cadence per App-data release: capture → diff → classify → packets → PRs → regenerate status, guides and changelog; roles and review points; CI freshness gate (Q6) |

#### Replay compatibility across content-set versions (U7a)

Today replay and persistence require the exact `engine_build_id`, a SHA over
the complete packaged runtime tree. Packaging a new content set therefore
changes the identity that every existing replay expects, even when its original
content is still packaged. Retention under D3 is meaningful only with an
explicit compatibility mechanism; ignoring identity mismatches is forbidden.

1. **Version-aware execution.** The runtime loads the content-set version named
   by the game configuration or replay artifact for each participating faction.
   Every generic handler and every justified named handler required by any
   packaged content-set version is retained until no packaged version
   references it; the Q2 parity check is evaluated against the union of
   packaged versions, not the current version alone. Tombstones govern
   current-version mustering, never historical availability.
2. **Certified compatibility record.** A newer build may reproduce an artifact
   exported by an older build only when a versioned, hashed
   `replay_compatibility` record lists the pair (`engine_build_id` of the
   producing build, content-set version) as certified. Certification is
   established by replaying retained golden artifacts actually exported by the
   producing build (decision records, event log, RNG state, viewer-scoped
   checkpoints for both players and the operator, final state hash) under the
   new build with exact equality. The record is regenerated and re-verified on
   every build that claims it; a failed or absent pair is not covered.
3. **Fail-closed fallback.** A replay whose (build, content-set) pair is not
   covered fails with a typed error naming the exact producing build and the
   repository tag that has it; the exact-build deployment is the only route for
   that artifact. Operator persistence recovery (Phase 18L) keeps its exact
   build requirement unchanged; U7a applies to historical replay only.
4. **Contract change.** U7a amends `contracts/` and
   `ADAPTER_DECISION_CONTRACT.md` to add the compatibility record, its
   verification and the fail-closed behaviour, with conformance scenarios,
   before S3c changes catalog generation. Until U7a is merged, every retained
   previous version is `exact_build_only` in the status artifact and no
   previous-version replayability is claimed.

Acceptance evidence for U7a and for every later transition that packages a new
content set: a golden artifact exported by the actual V build, containing a rule
retired at V+1 (a justified named handler where one exists), reproduces exactly
under the V+1 build; the retired content executes in that V replay and is
rejected with a typed reason in a new V+1 roster; a deliberately uncovered
(build, content-set) pair fails closed.

#### Layered invalidation (U4)

Layer A separates **immutable source provenance** from the **semantic
dependency fingerprint**. The transcription hash authenticates the retained
operative text under F00 (that text includes points rows such as the Exorcist
surcharge). A new observation therefore often has a new transcription hash
even when gameplay semantics are unchanged. The hash is never treated as a
semantic descriptor and never compared for Layer A equivalence.

| Layer | Claims | Evidence | Demoted when |
| --- | --- | --- | --- |
| A: semantic execution | L4, L5 | Provenance: source ID and the current observation's transcription hash, retained as immutable pins. Semantic fingerprint: effect RuleIR hash; timing/window descriptor; target grammar; restriction grammar; bearer grammar; binding IDs and parameters; handler identity for named-handler-backed clauses | The semantic fingerprint changes, or a transcription change cannot be classified / cannot be carried forward |
| B: roster legality | L6 | cost rows hash; composition hash; wargear/options hash; keywords hash; Leader/Support and attachment hash; army-construction constraint hash; geometry evidence IDs | Any roster-legality element changes |
| C: certification | L7, L8 | The current Layer A and B evidence of every entity in the certified rosters and interactions, plus the content-set version and packaged build identity | Any contributing Layer A or B semantic/roster element changes, or the content-set/build identity changes without a recorded re-attestation |

**Carry-forward.** A changed source transcription initially requires impact
classification. Existing Layer A execution evidence may be carried forward to
the new source observation only through a recorded equivalence review linking
the old and new transcription hashes and establishing that all applicable
semantic descriptors, bindings, and handler-backed clauses remain equivalent.
Points-only changes preserve unchanged Layer A evidence while invalidating
affected Layer B and dependent Layer C claims. Unclassified changes remain
stale.

A Layer A fingerprint change demotes L4–L8 for the affected entity and every
certified roster that uses it. Equality of the effect RuleIR alone never
proves equivalence: a changed WHEN clause, target set, restriction or bearer
text with an unchanged effect is a Layer A fingerprint change. For
named-handler-backed clauses, the carry-forward review must also confirm
handler identity and handler-backed eligibility; without that review the
claim stays `stale`.

**Layer C re-attestation.** Layer C always binds to a content-set version and
packaged build identity. Carry-forward of Layer A (editorial) or preservation
of Layer A while refreshing Layer B (points-only) never silently preserves
L7/L8 on the new identity. Those claims are re-attested: the status artifact
records the new content-set/build pins and the review or roster-validation
evidence that authorizes them. Until that re-attestation exists, L7/L8 for
the affected rosters are `stale` even when Layer A remains current.

Acceptance fixtures for U3/U4 (implementation tests required when U3/U4
land; this documentation PR only defines them):

1. Changed timing with unchanged effect IR and a new transcription hash
   invalidates Layer A (and dependent Layer C).
2. A reviewed editorial-only change uses different old and new transcription
   hashes, carries Layer A forward through the recorded equivalence review,
   and re-attests Layer C to the new content-set/build identity without
   requiring a semantic re-implementation.
3. A points-only change uses different old and new transcription hashes,
   preserves Layer A through carry-forward, invalidates affected Layer B
   claims, and re-attests dependent Layer C only after roster validation.

Impact classes assigned by U3:

| Class | Example | Layers demoted | Required work |
| --- | --- | --- | --- |
| Points only | Eldrad 130→120; Bloodcrushers surcharge 20→40 | B (affected rosters); C until re-attested | Regenerate cost records; re-run roster validation; carry Layer A forward with a recorded hash-link review that the semantic fingerprint is unchanged (points live in provenance text, not in the fingerprint); re-attest Layer C to the new content-set/build identity |
| Text hash equal | Page re-rendered, same operative text | none | Re-pin observation; provenance hash already matches |
| Editorial equivalent | Wording tweak; semantic fingerprint unchanged | C until re-attested | Record the equivalence review linking old and new transcription hashes; carry Layer A forward; re-attest Layer C to the new content-set/build identity. Named-handler-backed clauses require the review to confirm handler identity |
| Timing, target, restriction or bearer changed, effect IR equal | WHEN clause moves to a different window; bearer widened | A, C | Demote to `stale`; re-map and re-certify L4–L8 |
| Effect IR changed | Acts of Faith battle-round → turn start | A, C | Demote to `stale`; re-certify L4–L8 |
| Unclassified clause change | Classifier cannot attribute the diff | A, C | `stale` pending human review; no automatic carry-forward |
| Structural add | Nazdreg; Brute Bosses; a new Enhancement | n/a | Staging observation until official provenance is registered; then L0–L8 from scratch; no Python unless a new family is needed |
| Structural remove | More Dakka!; a removed Stratagem | C for rosters using it | Tombstone with `retired_in`; current-version mustering rejection regression; Python removed only when no packaged version references it |
| Attachment or keyword change | Eldrad's narrowed Leader list | B, C | Regenerate attachment records; fieldability regressions |
| Faction rewrite | Orks v946 | all, for the faction | U6 procedure |

Worked pilot (FM0.5, Orks): retain the two most recent Orks versions (the
931→946 pair is retained through versioned-path URLs under the S1 amendment as
the tooling fixture); the diff reproduces the feed; the classifier identifies
the adds, removals, DP changes, inventory swaps and "Rules Updated" units;
More Dakka! and every other removed detachment receive tombstones and rejection
tests; the Orks records are regenerated from the current content set; the
Waaagh! consumer is demoted to `stale` and re-certified against current clauses
(F-ORK-01). Orks is not certified at that point, so no previous Orks version is
packaged as loadable content.

### Track Q: quality gates and evidence

| ID | Deliverable |
| --- | --- |
| Q1 | One generated `content_status` artifact carrying the L0–L8 ladder, freshness, per-layer evidence tuples (U4), `blocked_provenance` staging observations kept distinct from admitted records, per-faction `first_certified_at_content_set`, and the replay-compatibility coverage of every packaged version (`certified` or `exact_build_only`). Guides, audits and the Phase 17O capability manifest derive from it. The four current coverage artifacts become inputs or are retired |
| Q2 | Code-quality audits: no faction, detachment, unit or datasheet identifiers and no display-name comparisons in generic engine modules (allow-list: faction content and source-linked provider registries); no dated runtime module names; content set ↔ Python parity evaluated against the union of packaged content-set versions (every faction Python module maps to a record in at least one packaged version; no module survives once no packaged version references it); every content-set JSON carries version and provenance; staging observations never appear in packaged data; no hand-maintained implemented-ID maps |
| Q3 | Hypothesis roster fuzzing per certified faction: generated legal rosters must muster; targeted illegal mutations (DP over budget, wrong disposition, retired unit, illegal bearer, over-cap ally, duplicate detachment) must be rejected with typed reasons |
| Q4 | Headless full-game harness over the certified-faction pairing matrix through the shared facade with exact replay reproduction and zero unsupported diagnostics; feeds the standing 60 s mean / 300 s maximum targets in `docs/performance/PERFORMANCE_POLICY.md` |
| Q5 | Performance evidence per policy for any hot-path family |
| Q6 | CI freshness gate: packaged content-set version versus the latest retained observation; stale certified claims fail unless acknowledged in the ledger |

### Track D: documentation

| ID | Deliverable |
| --- | --- |
| D1 | Guides and audits generated from Q1 only; no hand-edited status |
| D2 | Per-content-set changelog generated from U2/U3 |
| D3 | `ADAPTER_DECISION_CONTRACT.md` updated in the same PR as any new family or decision kind; `FACTION_AGENT_IMPLEMENTATION_CONTRACT.md` rewritten for data-first packets (records and bindings; Python only for a new family or a justified named handler) |

## Debt retired in FM0

1. `engine/army_mustering.py` content branches for Shadow Legion and Corsair
   Coterie and the Be'lakor display-name gate → source-linked provider entries
   on the Core P25C constraint surfaces.
2. Per-detachment `*_ir_support_2026_27.py` modules and
   `faction_detachments_2026_27.py` → content-set records (S3d).
3. `tools/generate_faction_content_scaffold.py`, its
   `IMPLEMENTED_CONTRIBUTION_IDS_BY_MODULE_PATH` map, the generated manifest
   scaffolding and the placeholder detachment modules → removed; runtime
   contributions are loaded from content-set bindings plus the remaining
   justified Python handlers. Handlers referenced by any packaged content-set
   version are retained (U7a); only unreferenced Python is deleted.
4. `chaos_daemons/july_2026.py`, `july_2026_candidate.py`,
   `july_2026_updates.py` → versioned data.
5. The Wahapedia snapshot, whose directory label names a retired edition →
   frozen legacy crosswalk with the label resolved (S3c).
6. Retired Orks scaffold directories → U5.
7. The runtime semantic coverage artifact pinned to the July execution
   package → Q1.
8. Death Guard `units/` and `wargear/` Python modules → RuleIR-first; Python
   only for a justified named handler.
9. F-ARMY-01 Acts of Faith trigger → corrected against current clauses with
   both players' turn starts, duplicate-trigger prevention, other gain sources,
   spending decisions, restore and replay; reference case for U4.

## Sequence

| Milestone | Contents | Exit criterion |
| --- | --- | --- |
| FM-pre | Documentation-only work permitted before Gate 0 (below) | Surveys and design documents merged; nothing under `src/`, packaged data, generators, registries or policies changed |
| Gate 0 | Core Rules roadmap PFINAL closed, including P25A–C; T4 delivered to P25C beforehand | Core completion commit recorded as the faction baseline; V0 selected |
| FM0 Foundation | S1–S5 (with S3a–S3d), T1–T6 regenerated, U1–U4 and U7a, Q1–Q2, debt items 1–9, D3 | Demand matrix published from retained content; status artifact live; catalog generated from the content set; committed army-list artifacts resolve unchanged; U7a merged and its golden-artifact fixture reproduces; the Orks 931→946 fixture reproduces the feed; no content branching in generic modules; no placeholder Python |
| FM0.5 Orks pilot (parallel with FM1-a) | U5–U8 on the two most recent Orks versions; F-ORK-01 | Retired detachments rejected from current-version mustering with typed reasons and their unreferenced Python removed (Orks has no packaged previous version, so historical availability is proven by the U7a fixture, not here); added detachments at L2 or `blocked_provenance`; Waaagh! re-certified or explicitly `stale` |
| FM1-a Chaos Daemons implementation | C-CD and the Track G families it demands; F-DATA-01 Bloodcrushers | Every Chaos Daemons entity at L5 or higher; at least three rosters at L7; every remaining blocker recorded per entity in the status artifact |
| FM1-b Chaos Daemons certification | Close every recorded blocker; Q3 fuzzing and Q4 pairing harness for Chaos Daemons; C-FINAL-style audit of the faction | Every owned or inherited Chaos Daemons entity L8 and `current` at the packaged version; zero open blockers; certification event recorded |
| FM2-a / FM2-b Emperor's Children | C-EC; Legions of Excess pact | Same criteria as FM1-a / FM1-b |
| FM3-a / FM3-b Aeldari | C-AE; Harlequins and Ynnari; F-DATA-01 Eldrad | Same criteria |
| FM4-a / FM4-b World Eaters | C-WE; Blood Legions pact | Same criteria |
| FM5-a / FM5-b Orks | C-OR | Same criteria |
| FM6+ Waves 2–5 | Data-dominant slices, each with its own -a and -b milestones | Rules unlocked per family and the share of new content needing Python are reported per wave; a rising code share stops the wave for family redesign |
| FM-FINAL | C-FINAL | Every in-scope entity L8 and `current` at one pinned version |

Progression rules between milestones:

1. FM(n+1)-a may start when FMn-a has closed.
2. FMn-b must close before FM(n+2)-a starts, so at most one priority faction is
   awaiting certification while the next is being implemented.
3. Wave 2 does not start until FM1-b through FM5-b have all closed.
4. An -a milestone never closes a blocker by omission. Missing geometry
   evidence, unresolved identity, `blocked_provenance` staging content, an
   `unsupported` clause or an open Core regression are recorded per entity and
   carried into the -b milestone; a -b milestone cannot close while any of them
   is open. If a blocker cannot be resolved (for example no acceptable geometry
   evidence exists for a model variant), the faction is not certified, its
   status says so, and previous-version retention does not activate.

The **first full-support certification** of a faction is the close of its -b
milestone: every owned or inherited entity L8 and `current` at the packaged
content-set version, zero open blockers, Q3 and Q4 green for that faction, and
the certification event written to the status artifact as
`first_certified_at_content_set`. From the next content set onward, that
faction's previous version is packaged (D3) and covered by U7a.

For Chaos Daemons specifically, the obligations already known to stand between
FM1-a and FM1-b are: the four review-blocked representative heights recorded in
the README (Bloodthirster, Lord of Change, Plaguebearers, Plagueridden) and S5
evidence for the remaining datasheets that have no accepted geometry record;
V0 revalidation of the five detachments and the datasheet components whose
execution claims predate the migration; official provenance registration for
any post-V0 addition still held in staging; and the F-DATA-01 Bloodcrushers
cost drift. Any obligation discovered during FM1-a is added to that list in
the status artifact rather than deferred to FM-FINAL.

Rough PR shapes, not time estimates: FM0 about 25–30 bounded PRs (the catalog
generation migration and U7a are the largest items); FM0.5 about 6–8; FM1-a
about 30–40 and FM1-b about 5–10; FM2 about 15–20; FM3 about 35–45; FM4 about
15–20; FM5 about 25–35 (each including its -b milestone); later waves shrink per
faction as families saturate.

### FM-pre: documentation-only work permitted before Gate 0

Permitted in parallel with the remaining Core Rules orders:

- this roadmap and its maintenance;
- T1–T6 surveys as documents under `docs/factions/taxonomy/`, with methodology,
  counts and observation fingerprints. T1 is delivered:
  [T1_STRATAGEM_WHEN_TAXONOMY.md](factions/taxonomy/T1_STRATAGEM_WHEN_TAXONOMY.md).
  T2 is delivered:
  [T2_EFFECT_TAXONOMY.md](factions/taxonomy/T2_EFFECT_TAXONOMY.md).
  T3 is delivered:
  [T3_BEARER_TARGET_CONDITION_GRAMMAR.md](factions/taxonomy/T3_BEARER_TARGET_CONDITION_GRAMMAR.md).
  T4 is delivered:
  [T4_ARMY_CONSTRUCTION_GRAMMAR.md](factions/taxonomy/T4_ARMY_CONSTRUCTION_GRAMMAR.md).
  T5 is delivered:
  [T5_RESOURCE_STATE_TOKEN_TAXONOMY.md](factions/taxonomy/T5_RESOURCE_STATE_TOKEN_TAXONOMY.md).
  T6 is delivered:
  [T6_DECISION_KIND_VISIBILITY.md](factions/taxonomy/T6_DECISION_KIND_VISIBILITY.md);
- the S2 identity model design document: ID registry scheme, crosswalk schema,
  Space Marines overlay model, related-army ownership;
- Track U design and runbook documents: impact classes, packet schema,
  retention policy;
- the Q1 status-artifact schema document;
- draft D3 contracts, marked draft until FM0 makes them binding.

Not permitted before Gate 0: any change under `src/`, packaged data artifacts,
generators, the source-authority registry, the F00 policy text, or catalog and
runtime identity. Pre-gate documents are planning evidence; FM0 regenerates
every artifact from retained content and reconciles it with the documents.

## Evidence required to close an implementation slice

Record the content-set version, faction/detachment/datasheet IDs, exact
clauses, descriptor and execution IDs, owning consumers, remaining unsupported
branches, test references and generated artifact hashes. State which ladder
levels actually passed. Update the generated status artifact; the guides
regenerate from it. Preserve history when a later content set invalidates a
previously certified claim.

Use focused regressions while iterating, then the repository's complete PR
gates after scope and architecture review. Tests use real domain objects and
the shared decision path. A loaded record, a documentation row, a mocked
handler or a successful extraction is not execution evidence.

## Re-audit policy

Each App-data release is handled through Track U: capture, diff, classify,
generate packets, implement, regenerate status and guides. Removals are
inspected as carefully as modifications. The absence of an update-feed entry is
not proof of equivalence when the packaged content set is older than the
observed version. The generated status artifact records the actual packaged
version and observation date; no inventory in this document is indefinitely
current.

## F00 completion evidence

F00 is implemented by the separate [faction source policy](FACTION_RULES_SOURCE_POLICY.md),
[retained JSON audit](../data/source_audits/maintained_app_mirrors/factions_2026_09_05.audit.json)
and [generated governance review](FACTION_SOURCE_GOVERNANCE_REVIEW.md). This closed
F-SOURCE-01. The selected target is App-data 946, English, observed 5 September 2026.
Three complete observations exercise all package kinds: Sororitas army rules,
Sanctified Orators and Exorcist. The Exorcist Hull/missing-height obligation
demonstrates the separate geometry-authority gate; fieldability remains blocked.

The typed offline loader authenticates retained text, complete-scope fingerprints,
owner/page identities, provenance and the full registered source-catalog hash through
`RuleEvidenceRecord` and `RuleSourcePackage`. Candidate validation rejects structurally
incomplete, conflicting, ambiguous and excluded-classification evidence. Human review
establishes provider-page completeness; the immutable byte pin authenticates the
reviewed capture and rejects even a structurally valid rehashed truncation. Catalog
source IDs are globally unique, and package version/date derive from the audit;
catalog metadata drift fails authorization. It reuses P14's
non-Core source normalization. Regressions are in
`tests/unit/test_faction_source_governance.py`; static artifact, provenance and
offline-boundary checks are in `tests/code_quality/test_faction_source_governance.py`.
The offline generator check is `uv run python tools/build_faction_source_governance.py --check`.

Only source load support is established; all three observations remain
`not_certified` for semantic execution and have no runtime consumer claims.
S1–S3 own corpus-wide retention, provider/catalog crosswalks and version
reconciliation. F-SCOPE-01 remains held for exact identity review, with no
Warbuggies admission. The Acts of Faith consumer correction is FM0 debt item 9.
No adapter decision or payload contract changes were introduced by F00.

After integration with `main` at `94972c20`, Order 18/P14 supplies the shared
objective-geometry query and explicit source `objective_scope` classification.
New faction source ingestion and objective effects must reuse those owners.
Faction-specific effects such as the Chaos Daemons corrupted-realspace aura
still require their own source and consumer review.

## Legacy workstream IDs

The guides under `docs/factions/guides/` and the audits under
`docs/factions/audit/` still reference the superseded F01–F09 identifiers.
Until D1 regenerates them, read those references through this map.

| Legacy ID | Superseded by |
| --- | --- |
| F00 | Complete; evidence above |
| F01 | S1, S2, S4 |
| F02 | T5, Track G resource families, Track C army-rule step |
| F03 | T1–T4, Track G, Track C detachment step |
| F04 | S3a, Q3, Track C datasheet step |
| F05 | S3a, Track G attack families, Track C datasheet step |
| F06 | S5 |
| F07 | T2–T3, Track G, Track C datasheet step |
| F08 | Q3, Q4, Track C fieldability and full-game steps |
| F09 | Q1, Q6, D1, C-FINAL |
