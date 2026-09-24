# CORE V2 Faction Rules Roadmap

[Faction guides and points](FACTION_SUPPORT.md) · [Observation register](FACTION_AUDIT_SOURCES.md) · [Source policy (F00)](FACTION_RULES_SOURCE_POLICY.md) · [Core Rules roadmap](CORE_RULES_REMEDIATION_ROADMAP.md) · [Architecture status](../ARCHITECTURE_V2.md)

## Where this stands

Faction implementation has not started. Gate 0 is core `PFINAL` in the [Core Rules roadmap](CORE_RULES_REMEDIATION_ROADMAP.md). That audit is Order 84 and is open after Order 83 merged in [PR #503](https://github.com/SobolGaming/Warhammer_40k_AI/pull/503). P25A–C are already merged; they do not close Gate 0.

F00 is complete: source policy, retained observations, and load support only. The three pilot observations stay `not_certified` for semantic execution. FM-pre design documents are delivered. FM0 and every later milestone are blocked on Gate 0.

[ARCHITECTURE_V2.md](../ARCHITECTURE_V2.md) Phases 17E and 17F are coverage and dispatch. Phase 17G slices are existing execution. This roadmap revalidates or retires that Python after Gate 0. It does not treat those slices as L8 certification.

## Decisions

Recorded 9 September 2026.

| # | Decision | Consequence |
|---|---|---|
| D1 | 40k.app is the authority for structured data and operative rule text | Generators move to a versioned content set. The Wahapedia snapshot becomes a legacy identity crosswalk. Official GW PDFs remain provenance |
| D2 | Orks update pilot runs beside the Chaos Daemons slice | FM0.5 exercises diff and retirement on the two latest Orks versions while FM1-a implements Chaos Daemons |
| D3 | Keep current plus one previous version per faction, only after that faction's first full-support certification | Before the -b milestone, package only the current version. After it, package the previous version and cover it with U7a, or report `exact_build_only` |
| D4, D7 | Core Rules orders close before faction implementation | Playable has no Core-exception list. Army-construction facts are Core P25A–C |
| D5 | Space Marines are a super-family | Shared detachments are certified once. Chapter views are overlays. Grey Knights is outside the overlay |
| D6 | Content is JSON with typed loaders | Python only for a justified named handler. FM0 removes the scaffold, generator, and placeholder modules |
| D8 | Documentation may proceed before Gate 0 | Only the [FM-pre list](#fm-pre-documentation-only-work-permitted-before-gate-0) |

## Scope

`AGENTS.md` exclusions apply: Forge World, Crusade, Boarding Actions, Kill Team as a separate game, Legends, and both Titan Legions. Matched-play Deathwatch datasheets named "Kill Team" are ordinary datasheets.

The September 2026 planning inventory, App-data 946, is 40 admitted views, about 982 datasheet URLs, 506 detachment URLs, 1,756 Enhancement or Upgrade entries, and 2,520 Stratagem entries including repeats. Distinct counts wait on S1 retention. Later milestones re-count at the then-current App-data version.

## Method

1. **Breadth, data only.** Retain pages, resolve identity, and classify every clause into a semantic demand matrix. No engine semantics in this loop.
2. **Depth, one priority faction.** Certify a vertical slice. Each new generic family is designed for every faction that needs it, with one priority consumer and one non-priority regression.
3. **Saturation.** Later factions bind data to existing families. A rising share of new Python stops the wave for a family redesign.

Implement next the family that unlocks the most rules in the current priority faction, when at least two factions demand it or a named-handler justification exists under `AGENTS.md`.

Design rules enforced at Q2: content is data; generic surfaces come from the demand matrix; identity is stable source IDs; no source version in module names; retirement is `retired_in` / `superseded_by`; one generated status artifact feeds every report.

<a id="status-and-acceptance-gates"></a>
## Content model and status ladder

Each entity has a project-owned ID, a crosswalk row, and a status record: faction view, army rule, related-army pact, detachment, datasheet, and content set.

| Level | Name | Evidence |
|---|---|---|
| — | Staging | No registered official provenance. Planning only. Never packaged. Reported as `blocked_provenance` |
| L0 | Observed | Retained page under the F00 contract |
| L1 | Loaded | Typed content-set record and crosswalk row |
| L2 | Structured | Datasheet costs, composition, options, keywords, Leader and Support. Detachment DP, disposition, Enhancement and Stratagem inventories |
| L3 | Geometry | Accepted base, hull, and height for every model variant |
| L4 | Mapped | Every clause maps to RuleIR, a generic family, a justified named handler, or typed `unsupported` |
| L5 | Executable | Real lifecycle consumer, deterministic replay, typed unsupported branches |
| L6 | Fieldable | One legal roster accepted and one illegal roster rejected with a typed reason |
| L7 | Playable | One headless full game through `AdapterGameSession` / `LocalGameSession`, exact replay, viewer-scoped projections, zero unsupported diagnostics |
| L8 | Certified | All variants, branches, negative cases, and cross-faction interactions at the pinned version |

Freshness is `current`, `stale`, or `retired`. A faction is fully supported at version V only when every non-retired entity it owns or inherits is L8 and `current` at V. Reports show counts per level. No single percentage is published.

A Stratagem is usable when it appears as `use_stratagem` at the right window with legal targets and CP, and executable when the effect applies through an engine-owned path. Enhancements have bearer grammar, an effect template, and use ledgers. Detachment rules have a condition, an effect, and army-construction constraints. Datasheet abilities are certified per unit and implemented per semantic family.

<a id="initial-findings"></a>
## Open findings

| ID | Priority | Finding | Owner |
|---|---|---|---|
| F-ARMY-01 | 1 | Acts of Faith grants a Miracle die at each turn start. The Sororitas consumer uses battle-round start | FM0 debt item 9 |
| F-ORK-01 | 1 | Orks v946 roster, DP, and inventory drift. Retired scaffold directories remain | FM0.5, then U5–U6 |
| F-DATA-01 | 1 | Current costs and attachments differ from older records (Eldrad, Bloodcrushers, Exorcist) | S3a, FM1, FM3 |
| F-EVID-01 | 1 | Status, source, execution, and component labels use different denominators | Q1 schema delivered. Live artifact is FM0 |
| F-OWN-01 | 2 | Shared URLs, chapters, and related daemon views are not one identity | S2 design delivered. Registry is FM0 |
| F-GEOM-01 | 2 | No model-height field on App datasheets. 17 pages lack a base field | S5 |
| F-CORE-01 | 2 | Shared Core Ability wording belongs to the engine | Gate 0 |
| F-DOC-01 | 2 | Guides are hand-maintained | D1 generation is FM0 |
| F-SCOPE-01 | 2 | Warbuggies reuses a historically excluded name | Unresolved in S2 |
| F-DEBT-01 | 1 | Generic mustering branches on faction content. Dated Python modules and per-detachment RuleIR remain | FM0 debt items 1–8 |

## Sequence

| Milestone | Exit |
|---|---|
| FM-pre | Design documents below are merged. No `src/`, packaged data, generators, registries, or policy changes |
| Gate 0 | Core `PFINAL` closed, including P25A–C. T4 was delivered to P25C. Record the core completion commit and select V0 |
| FM0 | S1–S5, regenerated T1–T6, U1–U4, U7a, Q1–Q2, debt items 1–9. Catalog comes from the content set. No content branching in generic modules |
| FM0.5 | Orks pilot beside FM1-a. F-ORK-01. Retired detachments rejected from current mustering |
| FM1-a / FM1-b | Chaos Daemons at L5+, then L8 and `current`, with Q3 and Q4 |
| FM2-a / FM2-b | Emperor's Children, including Legions of Excess |
| FM3-a / FM3-b | Aeldari, Harlequins, and Ynnari |
| FM4-a / FM4-b | World Eaters and Blood Legions |
| FM5-a / FM5-b | Orks |
| FM6+ | Waves 2–5: remaining Chaos, Space Marines overlays, Imperium, Xenos. Data-dominant |
| FM-FINAL | Every in-scope entity L8 and `current` at one pinned version |

FM(n+1)-a may start when FMn-a closes. FMn-b must close before FM(n+2)-a. Wave 2 waits until FM1-b through FM5-b close. An -a milestone records blockers; a -b milestone cannot close while any blocker is open. The -b close is `first_certified_at_content_set`. Previous-version retention starts on the next content set.

Priority slices at the App-data 946 count, re-counted at V0: Chaos Daemons (53 datasheets, 9 detachments), Emperor's Children (18, 9), Aeldari (55, 14), World Eaters (25, 7), Orks (53, 15).

Rough size, not a schedule: FM0 about 25–30 PRs; FM0.5 about 6–8; FM1-a about 30–40 and FM1-b about 5–10. Later factions shrink as families saturate.

### FM-pre: documentation-only work permitted before Gate 0

Delivered as planning evidence. FM0 regenerates artifacts from retained content.

- T1–T6 under `docs/factions/taxonomy/`
- [S2 identity model](factions/identity/S2_IDENTITY_MODEL.md)
- [Update classification, packets, retention, and runbook](factions/updates/README.md)
- [Q1 status-artifact schema](factions/status/Q1_STATUS_ARTIFACT.md)
- [D3 contract-rewrite draft](factions/contracts/D3_CONTRACT_REWRITES.md). Live adapter and agent contracts stay unchanged until FM0

Not permitted before Gate 0: changes under `src/`, packaged data, generators, the source-authority registry, the F00 policy text, or catalog and runtime identity.

## Tracks

Detailed designs live in the linked FM-pre documents. This table is the owner map.

| Track | IDs | Role |
|---|---|---|
| S | S1–S5 | Retain V0, identity registry, content-set extraction, Wahapedia crosswalk, version ledger, geometry authority |
| T | T1–T6 | WHEN, effect, bearer, army-construction, resource, and decision taxonomies. Planning JSON is not the demand matrix; FM0 regenerates that |
| G | — | Generic families from Track T, built inside the depth loop, two consumers or a named-handler justification |
| C | C-CD through C-FINAL | Faction slices: army rule, detachments, datasheets, fieldability, headless replay |
| U | U1–U8, U7a | Capture, diff, classify, invalidate, retire, rewrite, retain, replay compatibility. Tools are FM0 |
| Q | Q1–Q6 | One status artifact, content-neutrality audits, roster fuzzing, full-game harness, performance, freshness CI |
| D | D1–D3 | Guides generated from Q1. Live contract rewrite waits for FM0 |

U7a is a prerequisite of S3c. A newer build may reproduce an older artifact only when a hashed `replay_compatibility` record certifies that build and content-set pair by exact replay. An uncovered pair fails closed. Operator persistence recovery keeps its exact build requirement. Until U7a merges, a retained previous version is `exact_build_only`.

Layer A is semantic execution, Layer B is roster legality, and Layer C is certification. A transcription-hash change is provenance until impact classification carries the claim forward or marks it stale. Points-only changes keep Layer A and invalidate Layer B. The closed class set and fixtures are in [U_CLASSIFICATION_SYSTEM.md](factions/updates/U_CLASSIFICATION_SYSTEM.md).

## Debt retired in FM0

1. Content branches in `engine/army_mustering.py` move to source-linked providers on the P25C surfaces.
2. Per-detachment `*_ir_support_2026_27.py` modules and `faction_detachments_2026_27.py` become content-set records.
3. The scaffold generator, implemented-ID map, and placeholder detachment modules are removed. Python still referenced by a packaged content set stays until U7a allows deletion.
4. Dated Chaos Daemons runtime modules become versioned data.
5. The Wahapedia snapshot becomes a legacy crosswalk.
6. Retired Orks scaffold directories are tombstoned.
7. The July semantic-coverage artifact is replaced by Q1.
8. Death Guard unit and wargear Python moves to RuleIR unless a named handler is justified.
9. F-ARMY-01 is corrected against current Acts of Faith timing.

## Datasheet closure

Every admitted datasheet keeps a field table under `docs/factions/audit/`. A missing field is unresolved, not a default. Sir Hekhtur is included by Canis Rex and has no standalone cost. Model height needs an accepted geometry source beyond the App page.

| Surface | Owner |
|---|---|
| Points, composition, characteristics, wargear, options | S3a, Track C |
| Base and height | S5 |
| Keywords | S3a, Core P02D, Track G |
| Leader and Support | S3a, Core attached-unit rules, Track C |
| Abilities | Track G, then the faction slice |
| Transport and damaged profiles | S3a and the owning generic family |

## F00 evidence

F00 closed F-SOURCE-01. Target: App-data 946, English, observed 5 September 2026. Exercised observations: Sororitas army rules, Sanctified Orators, and Exorcist. Exorcist hull and missing height stay a geometry block. The offline loader authenticates retained text through `RuleEvidenceRecord` and `RuleSourcePackage`. Regressions are `tests/unit/test_faction_source_governance.py` and `tests/code_quality/test_faction_source_governance.py`.

Load support only. S1–S3 own corpus-wide retention and the catalog crosswalk. F-SCOPE-01 stays held. Order 18 / P14 supplies the shared objective-geometry query that new faction objective effects must reuse.

## Legacy workstream IDs

Guides and audits may still say F01–F09. Read them through this map until D1 regenerates them.

| Legacy ID | Superseded by |
|---|---|
| F00 | Complete; evidence above |
| F01 | S1, S2, S4 |
| F02 | T5, Track G, Track C army-rule step |
| F03 | T1–T4, Track G, Track C detachment step |
| F04 | S3a, Q3, Track C datasheet step |
| F05 | S3a, Track G attack families, Track C datasheet step |
| F06 | S5 |
| F07 | T2–T3, Track G, Track C datasheet step |
| F08 | Q3, Q4, Track C fieldability and full-game steps |
| F09 | Q1, Q6, D1, C-FINAL |
