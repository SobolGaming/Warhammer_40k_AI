# Faction audit: source and evidence register

[Faction directory](FACTION_SUPPORT.md) · [Remediation roadmap](FACTION_RULES_REMEDIATION_ROADMAP.md) · [S2 identity model](factions/identity/S2_IDENTITY_MODEL.md) · [Track U classification](factions/updates/U_CLASSIFICATION_SYSTEM.md) · [Track U packet schema](factions/updates/U_PACKET_SCHEMA.md) · [Q1 status artifact](factions/status/Q1_STATUS_ARTIFACT.md)

## Observation boundary

The 40k.app faction directory, update feed and linked pages were read in a browser on **5 September 2026**. The feed showed App-data **946 (2 September 2026)** as latest. Current URLs are mutable; the date and page fingerprints below identify this observation, not an indefinitely current source. 40k.app is a non-affiliated maintained App-data mirror, not a Games Workshop-owned website.

This documentation PR retains factual inventories, short review notes, links and observation fingerprints. It does not commit a bulk copy of operative rules or a runtime-ready source package. The detailed inventories were transcribed from observed page DOM; the temporary capture/extraction scripts are not shipped as repository generators. F00 must retain and validate approved complete source artifacts before any new runtime semantics or certification.

The existing [Core Rules source policy](CORE_RULES_SOURCE_POLICY.md) is limited to categories 01–25. Applying its evidence discipline here for planning does not silently extend its approved package scope. Existing official source packages keep their provenance and authority until the faction source contract is established.

**F00 follow-up:** the separate [faction source policy](FACTION_RULES_SOURCE_POLICY.md)
now establishes that contract. Its [retained review](FACTION_SOURCE_GOVERNANCE_REVIEW.md)
contains complete new observations for the Sororitas army page, Sanctified Orators
and Exorcist, under App-data 946. Their retained text and fingerprints replace no
historical inventory observations below. Remaining corpus retention and exact
provider/catalog reconciliation belong to F01; gameplay certifications remain open.

## Observed version ledger

| Version | Published | Use in this audit |
| --- | --- | --- |
| 946 | 2026-09-02 | Current faction/unit/detachment pages and latest changes; Orks require major retirement/replacement review |
| 931 | 2026-08-26 | Faction changed-item lists across the admitted views; changed costs, abilities and attachments, including existing component-report candidates |
| 925 | 2026-08-11 | Aeldari and Dark Angels changes between the July baseline and v931 |
| 913 | 2026-08-04 | Chaos Space Marines, Necrons and Space Marines intervening changes |
| 909 and earlier | 2026-07-22 and earlier | Historical entries visible in the global feed; not exhaustively reviewed as deltas in this PR. F01 compares each implementation’s actual retained baseline with the complete current source |

The update ledger covers the versions above, not a claim that the repository was fully aligned with v909. Missing an update entry never establishes unchanged behavior. For existing execution, the audit cross-references changed-item navigation and inspects current pages; it does not claim that every diff has been traced through every runtime branch.

## Scope and identity

The directory exposes 36 primary views. Titan Legions and Chaos Titan Legions are excluded under repository policy. Six linked related views add Harlequins, Ynnari, Blood Legions, Plague Legions, Legions of Excess and Scintillating Legions, producing **40 admitted views**. Six Marine chapter views lack separate repository faction reporting groups and use the Space Marines report only as baseline evidence. Related daemon/Aeldari reports likewise remain review groupings, not substitute catalog identities.

Unit navigation contains **2,095 admitted listing references**, resolved to **982 distinct current source URLs**. Each distinct unit URL has one owned audit block. **506 distinct detachment URLs** remain separate observations even when chapter pages inherit the same detachment. Their 1,756 Enhancement/Upgrade and 2,520 Stratagem entries include repeated content. Stable source IDs must resolve the distinct-rule denominator in F01.

Scope screening compared listing names with archived source classifications (`Source.json` and `Datasheets.json`, dated 2026-06-14, under `data/source_snapshots/wahapedia/`), then checked complete current-PDF review evidence in `data/source_manifests/faction_pack_datasheet_review_v1.json`. Historical-only excluded identities were withheld; Land Speeder and Wartrakks were retained because the manifest has complete current faction-pack review evidence. Historical classifications are an exclusion aid only; active operative rules must come from approved 11th Edition sources.

**72 listing references representing 46 distinct source URLs were withheld** by that screening, in addition to the two excluded Titan views. One of those identities, **Warbuggies**, remains a current-source ambiguity: the new App name overlaps a historical Legends entry. The [S2 identity model](factions/identity/S2_IDENTITY_MODEL.md) lists it unresolved with no `catalog_id`. The other exclusions follow the retained out-of-scope source classification. Reconcile exact current origin before changing any decision; a matching name alone cannot prove identity.

Identity layers, overlay membership, related-army owner/listing/host split, and grandfather-versus-allocate rules are closed in that S2 document. Exact distinct-rule integers after owner-versus-alias grouping remain `S2-HOLD-DISTINCT-COUNTS`.

Consequently, “all” in this audit means the admitted navigation corpus with these declared exclusions and hold. It is not a claim to inventory every Games Workshop publication, every sculpt, or every historical datasheet. No excluded content is scaffolded or exposed as supported.

## Field extraction and limitations

The unit observations include all displayed cost rows (1,742 total), model profiles, composition, ranged/melee profile names, option-section presence and list-entry counts, bases, keywords, Leader/Support recipient links, and Core/Faction/Unit/equipment ability names. They also flag additional source sections such as transports and damaged profiles. Detailed operative option/ability wording must be retained under F00 before implementing it.

981 unit pages display a Costs section. Sir Hekhtur does not display a standalone cost and must be resolved through its inclusion relationship. Seventeen pages have no base field. No inspected datasheet exposes a model-height field. Do not infer zero cost, a default base, a default height or missing gameplay semantics solely from source-section presence/absence.

Candidate matches use the source-owning faction (or its explicit reporting group) and normalized display name only to find historical evidence for human review. They are deliberately not runtime identity joins. Exact source IDs, variant semantics, attachment recipients and eligibility remain F01 obligations.

The detachment observations retain DP, force disposition and additional hero metadata as displayed, rule headings, every listed Enhancement/Upgrade with points, and every listed Stratagem with CP. A table’s `Behavior / next work` cell identifies review topics, not a complete paraphrase or certification of the effect.

## Observation fingerprints

Each detailed faction audit records index/army/detachment-list observation timestamps and SHA-256 fingerprints. Each unit and detachment block records the SHA-256 of its observed text. The input is UTF-8 `main.innerText` without further whitespace normalization; the initial global directory/feed captures use `body.innerText` and include navigation/footer text. These DOM fingerprints identify the observations and detect drift but do not replace retained operative source artifacts. Without the temporary raw captures, a reader can verify the facts at the links but cannot independently reconstruct the old hash after the live page changes.

| Global page | Observed UTC | Text SHA-256 |
| --- | --- | --- |
| [factions](https://www.40k.app/factions) | 2026-09-05T20:36:45.654Z | `8b9c6ab5fe8e80d4082ef2ddb800a15453e719fe89da36b507e2b1a8124c0a11` |
| [updates](https://www.40k.app/factions/updates) | 2026-09-05T20:36:35.214Z | `9ffcc106cd467b418a3ac862efbd05c8ab64c730e6601f0fa3ba331b2f2c5202` |

All owned unit and detachment source URLs are linked in the [40 detailed audits](FACTION_SUPPORT.md#faction-directory). Their per-page fingerprints supply the remainder of this source register.

## Repository evidence

Baseline commit: **`52673fa1`**, the `main` revision selected when the documentation worktree was created. These hashes are over committed file bytes and are reproducible from that revision. No generated evidence was edited in this PR.

Integration was rechecked after merging `main` at **`94972c20`** (Order 18, PR #423). All four faction evidence artifacts below are byte-identical to the observation baseline, so their hashes and historical coverage counts remain valid. The new shared objective geometry and explicit source terminology scope are implementation prerequisites to reuse; they do not certify the remaining faction-specific objective effects. The original source-observation date and baseline are preserved rather than relabeled as a new audit.

| Artifact | Purpose | SHA-256 |
| --- | --- | --- |
| [data/generated/ability_coverage/datasheet_support_rows.json](../data/generated/ability_coverage/datasheet_support_rows.json) | 59 component-status rows | `027d430f04a0c6ccc16d35d357ab5a7f8500390e6191c5af73e11767c9ddd71b` |
| [data/generated/ability_coverage/ability_coverage_rows.json](../data/generated/ability_coverage/ability_coverage_rows.json) | Per-ability stages and consumer evidence | `89434c4ef000f4857af705fe2cb18194d2cfc7a5406734f91d331c85170158f7` |
| [data/generated/ability_coverage/runtime_content_semantic_coverage.json](../data/generated/ability_coverage/runtime_content_semantic_coverage.json) | Faction/detachment module classifications | `8aea32168c72dce6c56c7171b370da2174495fbc73533c79f861c5470353acbc` |
| [data/source_manifests/faction_pack_datasheet_review_v1.json](../data/source_manifests/faction_pack_datasheet_review_v1.json) | Reviewed current-PDF source scope | `c285b35718ac59c031423378bd0410fd749d117f62d109e3262e71a74485b94b` |

The source/execution comparison additionally reads `faction_coverage_2026_27.coverage_rows()` and its exact execution records through the same helpers used by [the ability support generator](../tools/generate_ability_support_matrix.py). It preserves execution classification separately from source `runtime_support_status` and consumer IDs. The source package remains the authority for those baseline fields. The [Q1 status-artifact schema](factions/status/Q1_STATUS_ARTIFACT.md) names these four files as inputs, not as the publishable ladder.

July costs in the unit audits come from the per-faction JSON artifacts in `src/warhammer40k_core/rules/source_packages/warhammer_40000_11th/mfm_2026_07/artifacts/factions/`. A missing or ambiguous candidate is explicitly unresolved. No current cost is silently filled from the July record.

## Refresh procedure

1. Record the repository commit and the update feed’s latest observed version/date.
2. Enumerate the current admitted faction navigation; reconcile excluded/ambiguous identities and inherited source URLs.
3. For existing execution, compare the exact retained baseline with all applicable changes and complete current clauses. Record stale and removed rows as well as unchanged ones.
4. For missing content, enumerate current army rules, detachment subrules and every unit field. Keep source presence distinct from engine support.
5. Retain approved source artifacts under F00; link each clause to descriptors, consumers and meaningful regression evidence.
6. Refresh the guides, audits and status gates together. Confirm every admitted URL has an owned audit and every guide link resolves. Do not promote historical report labels to full support without F08/F09 evidence.
