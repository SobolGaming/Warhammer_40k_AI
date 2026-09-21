# Order 69 / P25C: detachment construction constraints

Finding C25-04. Base: `28df017e` (Order 68). Implemented and validated.

The invariant is that every selected detachment's construction restrictions must
be represented as typed, source-linked data and enforced by the shared roster
validator. A catalog alias cannot select the same canonical detachment twice.
Every Support unit must join an eligible Bodyguard; the legality report and
army construction must agree about that obligation.

The authoritative path is retained Core 25.04 evidence -> closed Core catalog
records -> catalog link validation -> DetachmentSelection and ArmyMusterRequest
-> shared roster validation and UnitFactory -> ArmyDefinition -> GameConfig,
setup through LocalGameSession, projections, authenticated persistence and replay.
The catalog owns identity and constraints; the engine owns evaluation, selected
model reconstruction and attachment formation. No adapter independently evaluates
these rules. Fixed pre-game input remains covered by the existing adapter decision
contract; no in-game decision type is introduced.

The bug-class audit found that unit grants were incorrectly treated as exhaustive
faction-unit allow-lists, including rejecting an empty list as missing source.
The generator also rejected empty Enhancement/Stratagem inventories. Empty
inventories are now legal when their source columns are present; a missing column
is still an error. Faction admission remains independently validated. The report
previously omitted Support/attachment validation, while muster_army enforced it.
Both now use the same formation validator, extracted from the oversized
army_mustering module before adding the new behavior. Its existing source-support
metadata and architecture audit follow the extraction.

## Source and T4 resolution

The [T4 family catalog](factions/taxonomy/T4_ARMY_CONSTRUCTION_GRAMMAR.md) remains
read-only planning evidence. Its four construction families are implemented with
synthetic Core fixtures only. No faction constraints, pact families, content
handlers, display-name gates or keyword-text parsing are introduced. Existing
faction-specific mustering branches remain FM0 work.

The complete relevant [25.04 clauses](https://www.40k.app/rules/25-muster-armies)
were observed through the search index; the direct fetch returned 403. The
reviewed input, offline generator, source package, typed pinned loader and authority
registry retain provider, exact text, observation timestamp, hashes and historical
official-source provenance. No direct official-App capture or App-data version is
claimed. Reproduce with
`uv run python tools/build_core_roster_construction_source.py --check`.

T4's proposed force-disposition intersection is contradicted by retained source
evidence. Core 25.04 grants access to dispositions through each chosen detachment.
Games Workshop's [Chapter Approved explanation](https://www.warhammer-community.com/en-gb/articles/p3i6aa3h/the-chapter-approved-deck-what-is-it-and-how-does-it-work/)
(28 May 2026, sections "Varied Battles for Everyday Play" and "Chapter Approved and
the Event Companion") explicitly describes an army combining a Take and Hold
detachment with a Priority Assets detachment, then choosing its disposition.
The [official Event Companion](https://assets.warhammer-community.com/eng_12-06_warhammer40000_event_companion-s3bfb5f9s1-ivswuij3fo.pdf)
requires one available disposition to be recorded on the roster. Therefore P25C
certifies the existing union and the single selected disposition, rather than
introducing an unsupported restriction. Tests retain the disjoint-disposition
combination and reject an unavailable selection. Extra listing tags are not added
to the disposition inventory. This resolves the planning interpretation, not a
disagreement between maintained App mirrors.

## Data and evaluation contract

DetachmentDefinition requires canonical_detachment_id independently of its catalog
row ID. Existing generators explicitly retain their current project identities;
aliases must supply the same canonical ID. construction_constraints is a required
serialized list, empty in shipped content. Stable constraint/source IDs survive
round-trip and appear in deterministic violations. Unknown referenced datasheets
and canonical detachments fail catalog validation.

The closed UnitSelector union contains datasheet IDs, canonical keyword all/any/none
filters (including CHARACTER, EPIC HERO and BATTLELINE), numeric characteristic
thresholds with explicit any/all selected-model quantifiers, conjunction,
alternatives and exclusion. Keyword membership comes from UnitFactory's selected
models after structured mustering grants, including faction keywords. Thresholds
inspect selected roster model characteristics, never an unselected profile.
Non-numeric or unsupported predicates return a typed invalid diagnostic.
All children are evaluated so a successful alternative cannot conceal invalid data.

The separate DetachmentSelector contains a closed canonical-ID set with exclusions.
"Other" always excludes the owning detachment. Required constraints need a match;
prohibited constraints forbid every match. All selected owners are evaluated;
requirements never override prohibitions. The report is deterministic and
source-attributed, and construction constraints cannot be disabled by the existing
test-only relaxed points/Warlord flag.

The existing per-validation model resolver shares UnitFactory reconstruction
between constraints, attachments and bearer validation. No cross-request cache
or new gameplay state is introduced. Attachment formation remains the sole owner
of Support eligibility, source wargear, role limits and non-overlapping membership.

Contract 34, persistence v26, replay v28 and canonical catalog v2 reject old
catalog payloads explicitly. Existing faction catalog artifacts are regenerated
with empty constraints and explicit canonical identities; this is a schema
migration, not faction-rule population. See [33-to-34](../contracts/migrations/33-to-34.md).

## Validation

Focused tests cover the four families, owner exclusion, canonical aliases,
selector combinations, keyword grants, model-profile selection, malformed and
cross-domain records, unknown references, empty inventories, Support attachment,
deterministic payloads and session persistence. Existing behavioral files are
extended; the eight-shard file inventory remains unchanged.

Performance assessment reuses the existing Order 68 small/medium/large roster
workload and its unchanged ratio/additive budget. Base was measured before
implementation. Current-runtime Order 64/65/66 evidence has also been refreshed.
These component measurements do not certify complete gameplay or full-game targets.
The scope/diff audit confirmed no faction population or unrelated subsystem work;
the remaining file churn is explicit fixture identity and generated contract data.

The first aggregate found two stale expectations (the source-package count and
projection identity hashes); both were updated and their focused tests passed.
A second 64-worker aggregate passed all Order 69 tests but hit an unchanged
geometry test's Hypothesis input-generation health check (two integer inputs in
1.84 seconds). All sixteen geometry tests passed serially with the reported seed
in 0.37 seconds. The final complete coverage run retained every test and health
check, using xdist work stealing with `PYTEST_XDIST_AUTO_NUM_WORKERS=32` to reduce
host contention. No production code or performance budget changed.

Final local validation passed **8,610 behavioral tests at 85.14% coverage** and
**564 code-quality tests**. Behavioral coverage used 32 workers for the diagnosed
host-contention issue; quality used the default 64. Both used work stealing;
quality ran without coverage. The source-inventory quality checks were updated
for the new package after their first aggregate exposed the two omitted entries.
No production code changed after the qualified performance measurements or
behavioral coverage run.

Ruff check/format, mypy, pyright, all eleven import contracts, pre-commit and the
exact eight-shard check passed. The source generator, both canonical catalog
generators, engine identity and external contract check against `28df017e` passed.
The installed wheel validated 27 schemas and six request families. The generated
TypeScript client/typecheck, five unit tests and all 342 live conformance
assertions passed. This host lacks npm, so Node executed those package-script
equivalents directly. See [machine-readable validation and diagnostics](performance/order69/validation.json)
and [matched component results](performance/order69/README.md).
