# Order 67 / P25A: Incursion mustering limits

Status: implemented and locally validated; awaiting PR review and merge.
Finding IDs: C25-01, C25-02.
Dependencies and evidence gate: P00 and source governance merged; APP-AUTHORITY.
Base: `7cc632e8` (Order 66, PR #486); no other roadmap PR was open.

## Invariant and scope

A roster must respect its selected battle size. Incursion allows 1,000 points,
2 DP, 2 distinct Enhancements and 2 copies of an ordinary datasheet. Either
BATTLELINE or DEDICATED TRANSPORT independently doubles the copy limit to 4;
having both does not double it again. EPIC HERO uniqueness still takes precedence.
A single 3-DP detachment is expressly allowed, while 2+1, 1+1+1 and 3+1 are not.
Up to three assignments of one Upgrade consume one Enhancement selection, and
every assignment pays points.

Previously Incursion reused Strike Force's 4/3/6 Enhancement/ordinary/Battleline
limits. Dedicated Transport had no independent duplication exception at any size.
The corrected shared predicate also restores the same omitted exception for
Strike Force. The existing 3-DP exception and Upgrade accounting already follow
the operative clauses and are certified without replacing them.

Order 68 owns model-specific Warlord/Enhancement bearers and Upgrade eligibility;
Order 69 owns source-neutral detachment constraints and Support attachment.
This PR neither certifies those paths nor imports faction rules. In particular,
the existing Character-Upgrade rejection remains an Order 68 eligibility issue.
The observed table lists Incursion and Strike Force; existing Onslaught settings
are not newly certified by this observation. No out-of-scope content is ingested.

## Source evidence

Provider: 40k.app, a non-affiliated maintained direct App-data mirror under
`core-rules-source-policy:maintained-direct-app-data-mirrors:2026-09-02`.
URL: <https://www.40k.app/rules/25-muster-armies>.
Observation: `2026-09-20T18:08:38Z`; complete relevant clauses were available in
the search index while direct fetching returned 403. No App version, direct
capture, second-provider corroboration or co-version equivalence is claimed.
The reviewed table, duplication footnote, single-detachment exception and Upgrade
accounting clause are separate from the deferred bearer-eligibility clauses.

| Stable source ID | Transcription SHA-256 | Source-observation fingerprint |
|---|---|---|
| `gw-11e-core-mustering-limits:battle_size` | `4814d68cd7b6f065e97e3d2837fddff188d7db51c63679c403628bd0ee2f78fb` | `4d7d11426852168a7af4e046491d4a9dbaffc410c85a7ae3522aa1a936a18858` |
| `gw-11e-core-mustering-limits:single_three_dp_detachment` | `ccdcec776c186d934bbeefe61307a9608dfa47e95b0b4e95f0f18cd3add37835` | `dd91074ee77f598234310e9b1090b2b0c29a68f4918aaa0afd33ceaf7ffbf6d3` |
| `gw-11e-core-mustering-limits:upgrade_accounting` | `498817660ab2a921958720521432effaa22aab043f571bf3224706622bbf8dc7` | `48f6bb2d0771b54d4dee0c948d7a5887c4a303f3309cc4b445a238ad5084ca20` |

The artifact and maintained-mirror audit retain separate loaded/executable status,
registered provider/URL/timestamp tuples and the historical official Core Rules
PDF hash. `tools/build_core_mustering_limits_source.py --check` reproduces both
offline. The typed package loader eagerly rejects byte, schema, source-identity,
transcription or provenance drift. Its reviewed JSON and source-authority registry
pins are committed. No live lookup or runtime text parsing is added.

## Owning path and same-bug-class search

`BattleSizeMusteringPolicy.incursion` owns numeric defaults.
`validate_detachment_selection` owns the DP total and single-detachment exception.
`validate_roster_legality` owns the combined report; its duplication check delegates
to `roster_unit_limits.datasheet_unit_limit`, consuming canonical catalog keywords.
The prior predicate was extracted before extension; the oversized mustering
module shrinks. There are no dependency-boundary changes, new handlers, fallbacks
or integration stubs.

`DetachmentSelection.enhancement_ids` stores unique selected identities, while
`EnhancementAssignment` stores each paid copy. `_append_enhancement_violations`
checks selection limits, ordinary uniqueness and the three-copy Upgrade limit.
`_append_unit_point_violations` charges each assignment, including the separate
source-backed roster-points ledger. Existing MFM/player-list regressions exercise
that alternative ledger. The audit searched all battle-size factories, unit-limit
consumers, enhancement accounting, player-list import, roster-point overlays and
muster reconstruction. No second Core duplication validator was found.

`muster_army` consumes the report and rejects illegal strict rosters before returning
an army. Player army lists, setup, LocalGameSession and restore reconstruction
consume that same authority. The existing non-strict diagnostic fixture mode still
records violations; this PR does not expand it. No new in-game player choice or
mutation/event/replay path is introduced.

## Decision and viewer-visibility impact

Existing roster request, report and assignment payload shapes remain unchanged.
No new decision type, proposal, option family or viewer-visible field is added.
The existing adapter contract covers fixed pre-game roster inputs and their shared
validation. Exact runtime build identity prevents restoring old-engine snapshots
as this engine. Facade coverage verifies both viewer projections after persistence
restore and rejects an over-limit roster through setup. The contract bundle is
regenerated for the new engine identity without a public schema migration.

## Regression and architectural audit

The first corrected-fixture run reproduced six failures (Incursion defaults,
ordinary/Battleline/combined-keyword boundaries and independent Dedicated Transport
limits at both sizes), with nine passing control cases. All now pass.
Tests use real catalog/request/army objects, cover exact and one-over boundaries,
2-DP compositions versus the single 3-DP exception, one/two/three/four Upgrade copies,
2 versus 3 distinct Enhancements, the 1,000/1,001-point boundary, deterministic JSON
round-trips, typed rejection and facade persistence. Existing tests retain Epic Hero
uniqueness, ordinary Enhancement uniqueness and attached-unit constraints.

The scope/diff audit limits production changes to three Incursion constants and
one shared duplicate predicate. Source governance and generated identities are
supporting artifacts; adjacent eligibility/constraint repairs stay in their owning
orders. Static quality checks enforce the single predicate, direct canonical
keyword consumption and offline generator reproducibility. No behavioral test file
was added, removed or renamed, so shard membership is unchanged and checked.

## Validation

Focused mustering, roster points and player-list tests: 147 passed.
Focused source-artifact/module-size audits: 41 passed.
Matched component evidence and reproduction commands: [performance/order67](performance/order67/README.md).
The first aggregate attempt was interrupted after the source generator exposed
a Windows CRLF/LF mismatch. JSON semantics were identical, but the raw pins
would not survive a normalized checkout. Artifact/registry bytes and pins were
corrected before regenerating runtime identity; that attempt is not final evidence.
The first completed coverage run passed 8,521 cases at 85.13%, with one stale
source-registry inventory assertion (43 packages instead of the new 44). Only
that behavioral expectation and its matching static inventory assertion changed;
both focused regressions passed before the final respective aggregate gates. Production and runtime identity remain unchanged.
The final behavioral run passed all 8,522 tests with 85.13% coverage. The first
full quality run passed 552 checks and rejected two stale runtime timing records
from Orders 64/65. Both workloads were measured afresh, serially without competing
test/build workers, on the final runtime with unchanged baselines and budgets.
Their focused comparison guards passed before the final quality rerun.
The final quality rerun passed all 554 checks without coverage. Both final suites
used 64 xdist workers with work stealing. Ruff, formatting, mypy, Pyright,
11 import contracts, pre-commit, the exact eight-shard check, source/runtime
generators and exact-base contract compatibility passed. Installed-wheel smoke
covered 27 schemas and six request families; TypeScript client/type checks,
five unit tests and 342 live conformance assertions passed. No production code
changed after final behavioral validation. Machine-readable results and diagnostic
history are retained in [validation.json](performance/order67/validation.json).

PR URL: https://github.com/SobolGaming/Warhammer_40k_AI/pull/487.
Merge commit: pending; not merged.
