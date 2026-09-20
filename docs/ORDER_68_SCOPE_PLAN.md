# Order 68 / P25B: model-specific roster selections

Status: implemented and locally validated.
Finding: C25-03. Base: `6c10581d` (Order 67 merged, no open roadmap PR).

The invariant is explicit, persisted physical-model identity for Warlord and
Enhancement bearer selections. Only the selected Warlord model receives WARLORD;
the existing P02D model-presence authority derives unit keywords. Ordinary
Enhancements require an eligible Character model, Epic Hero exclusion applies to
the bearer model, and Upgrades additionally permit non-Character units. A
cannot-be-Warlord restriction takes precedence over mandatory Warlord selection.

The authoritative path is fixed pre-game roster input -> ArmyMusterRequest ->
roster validation and UnitFactory model ownership -> ArmyDefinition -> runtime
Enhancement activation and shared bearer queries -> model effects, split lineage,
viewer projections, persistence reconstruction and replay. Source inventory
authenticates identity; live physical inventory owns wounds and presence.

The bug-class search found first-model inference in enhancement_bearers and
generic_enhancement_effects, a single-model restriction in the generic
selected-to-fight consumer, whole-unit Warlord grants in army_mustering, a downstream single-model Deadly Demise restriction, and a
Character-Upgrade prohibition in its roster validator. Existing faction-specific
rules and Order 69 detachment constraints remain separately owned.

Source review: the complete relevant 25.04 clauses were observed in the 40k.app
search index on 2026-09-20. Direct fetching returned 403. The provider is the
non-affiliated maintained mirror recognized by the repository source policy;
no direct official-App capture or App-data version is claimed.
URL: https://www.40k.app/rules/25-muster-armies.

The existing oversized army_mustering module loses the Warlord/Enhancement
validation responsibility to roster_bearer_validation. The small shared
roster_model_identity module resolves required profile-local indexes against
immutable source inventory; enhancement_bearers resolves current physical ownership.
No architecture boundary, named handler, generic hook family or decision type is
added. Source-specific providers retain their existing semantics; Order 69
constraints remain separate. Extracted code is existing CORE V2 code, not legacy.

Both roster selection records require model_profile_id and positive one-based
model_index. Validation instantiates the selected composition through UnitFactory,
uses a per-call resolver to share repeated selected-unit reconstruction,
checks the selected model's canonical keywords and rejects missing/out-of-range
selections. Warlord grants modify exactly that model; P02D continues deriving unit
keywords from living members. Ordinary Enhancement Character and Epic Hero
restrictions, and generic keyword requirements, inspect the selected model.
Upgrades also allow Character bearers. Explicit and existing allied-unit Warlord prohibitions remove a
mandatory candidate and still rejects selecting it.

Runtime Enhancement assignments carry bearer_model_instance_id. Generic aura,
this-model and selected-to-fight consumers use it; Deadly Demise authenticates
membership rather than requiring the source unit to contain one model. Shared
bearer queries follow split lineage, including a non-first profile-local model,
and never transfer the assignment after death. Source models authenticate identity;
live models continue owning authoritative physical state.

The source package retains two reviewed clauses, offline generator, typed pinned
loader, observation audit and registry entries. The Order 67 artifact changes only
its consumer path after extraction; its reviewed source remains unchanged.

Contract 33, replay v27, persistence v25 and player-list v2 explicitly reject older
selection records. See [32-to-33 migration](../contracts/migrations/32-to-33.md).
Committed example lists record their formerly executed bearer identities; arbitrary
external lists require explicit selections. The existing fixed pre-game input
path remains shared by adapters, reconstruction and replay, as documented in
[the adapter contract](ADAPTER_DECISION_CONTRACT.md). No in-game choice or hidden
information policy changes. Facade tests compare both viewers after restoration
and reject saved selection drift against the independently rooted configuration.

Regression coverage includes mixed Character/non-Character/Epic profiles,
non-first Warlord and bearer, ordinary/Upgrade restrictions, invalid indexes,
unknown Warlord profiles, cannot-over-must precedence, corpse keyword presence,
split/fork identity, generic model effects, deterministic payload round-trips,
source-pin drift and facade persistence authentication. The prior lethal-damage
regression retains its FNP continuation and replay checks with a refreshed game ID:
adding explicit assignment fields changes its deterministic roll context.
Static audits forbid first-model indexing in shared bearer consumers and whole-unit
Warlord grants, and reproduce the reviewed source offline. Existing behavioral
files are extended; shard membership is unchanged.

Focused iteration found and repaired a downstream Deadly Demise singleton guard;
three contract failures in the same diagnostic run came from generated artifacts
being updated during execution. A final audit also found allied mandatory candidates wrongly blocking another
Warlord despite their existing prohibition. Their regressions now require
cannot-over-must precedence; an in-progress coverage run was stopped to include
that correction. These are not final validation results. Final gates
run only after runtime and generated artifacts are stable.

Performance evidence and final validation are recorded in
[performance/order68](performance/order68/README.md). This pre-game component
assessment does not certify gameplay-slice or complete-game targets. Required
exact-runtime Orders 64/65/66 evidence is refreshed without changing their budgets.

The initial roster timing comparison exceeded the predeclared small-roster budget
because Warlord and Enhancement checks reconstructed the same unit independently.
The per-validation resolver removes that duplication without retaining state across
calls. A real profiler regression covers the work bound and changed-input rejection;
all corrected mean/maximum comparisons pass with the unchanged budget. The initial
machine-readable timing evidence is preserved alongside the qualified reports.

The extraction reference audit updated the two Warlord consumer references in the
ability-support generator and regenerated its JSON rows and Markdown matrix. A
second incomplete coverage attempt was stopped before this reporting-code change;
the final aggregate starts from the complete stable tree. Runtime identity is
unchanged by the reporting correction. All removed-function metadata references
were searched; only these two active reporting rows required migration.

The first completed aggregate passed 8,538 tests with six fixture/assertion failures
and 85.13% coverage. The corrections add the required bearer-model field to a
hand-built invalid-authority fixture, check actual secret JSON keys rather than
the substring `mode` inside the new source ID, and refresh explicit game IDs for
real casualty/FNP branches. DiceRollManager seeds from event history, so both new
selection fields and source attribution affect these deterministic fixture streams.
The leader/support case now explicitly requires a failed Battle-shock test and
checks retained membership including destroyed Bodyguard models separately from
living model authority. No production code changed for these corrections.
The seven-case focused regression group passed, including the previously passing
control variant; the final complete coverage run follows these test-only updates.

Final local validation passed 8,544 behavioral tests at 85.13% coverage and all 558 code-quality checks. Both suites used 64 xdist workers with work stealing; quality ran without coverage. Required lint, type, import, shard, source/runtime/contract generator, package, client and live-conformance gates passed.
No production code changed after the final behavioral run began. Exact results, warning count and diagnostic history are in [validation.json](performance/order68/validation.json).
