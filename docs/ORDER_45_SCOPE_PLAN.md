# Order 45: phase-end Fire Overwatch

P15H / C15-08, based on main `a178a9e1ff5cac93c0c79e61499b2ce45f402012`.

## Invariant and source authority

At the end of the opponent's Movement phase, Fire Overwatch selects an eligible
friendly unengaged non-TITANIC rules unit. Its canonical Snap Shooting declaration
chooses one eligible visible enemy within 24 inches of that rules unit, independently
of movement or setup history. Invalid choices must not spend CP, pop the request,
or mutate authoritative state. Shooting completes before phase-end continuation;
the existing Snap hit, reroll and post-shooting Action restrictions remain in force.

The reviewed 15.08 and 15.09 text and complete provenance already reside in
`core_stratagems_2026_08/artifacts/package.json`, built by
`tools/build_core_stratagem_app_source.py`. Their transcription hashes are
`7cbb6c048a5c5420b2209a7c585b6063dafebfbca4f1d6e52af607282c77c8f0` and
`d9a660775aab4e7e07277850b27f2930682a232115bc720c81cb1618b50c5545`.
The retained maintained-App observation is authoritative under the repository's
approved source policy. A live 40k.app fetch returned HTTP 403 during this task;
no new live observation or source revision is claimed.

## Owning path and bug-class audit

Movement-end sequencing owns one opponent Overwatch occurrence. The Stratagem
target policy validates the shooter before spending; shared shooting eligibility,
candidate generation and proposal validation own targets and Snap constraints.
The existing out-of-phase state owns the attack, selected-to-shoot grants and
reaction continuation. Decision/event journals and lifecycle checkpoints preserve
the same authority for local, network, headless and replay consumers.

The bug-class search found movement-history enumeration, trigger-dependent
Stratagem availability, trigger-specific shooter range/target validation, handler
target binding, and a second trigger reconstruction in declaration validation.
The shared Snap request checked unit range while validation checked firing-model
range. Target protections and runtime restrictions must remain effective through
the shared candidate path. These are parts of the same target-choice invariant.
No new named handler, generic hook family, architecture boundary, faction support
or neighboring roadmap order is required.

## Acceptance

Cover no movement, stationary and moved enemies; one phase-end occurrence;
both eligible target choices; one-target Snap enforcement; 24-inch boundaries,
visibility, weapon range and source restrictions; unengaged non-TITANIC living
shooters, Battle-shock, shooting eligibility and Action locks; stale/malformed/
drifted submissions before mutation; CP and decline; attached rules units;
pending restore, exact replay, viewer projections and event deltas; grant and
attack interruptions followed by correct phase-end continuation.

Validation runs the complete behavioral suite with coverage, followed by the
code-quality suite without coverage. Matched performance evidence covers the
changed slice and neighboring phase-end continuation. Complete-game performance
is not certified by these workloads.

## Implementation and scope audit

One phase-end candidate replaces per-moved-unit enumeration. The existing
Stratagem target policy and shooting candidate owner validate every eligible
proposed shooter/target before use; loaded target-restriction hooks reach both
submission prevalidation and mutation. Optional window discovery retains the
standard parameterized-proposal contract so declining does not require solving
all possible shots. Shared shooter checks suppress the window when no living,
present, unengaged non-TITANIC unit can shoot, or no source-permitted enemy is
present. Exact shot eligibility remains a submission check. The request,
source-scope validator and Snap type validator consume
the same rules-unit presence, protection and 24-inch authority. Unknown target IDs
are rejected before geometry lookup, and forced-type candidates with no valid Snap
option carry a typed invalid diagnostic.

The existing core Stratagem orchestrator delegates to shared shooting, preserving
selected-to-shoot grants, CP, attack interruptions, Action restrictions and parent
reaction continuation. No named-handler budget, architecture boundary or reusable
semantic family changes. Broad-looking split-module diffs remove exports/imports
of the deleted trigger helpers; they do not add responsibilities to those modules.

The source texts and observation hashes are unchanged. Both source rows now record
`executable_engine_runtime`, with regenerated package/provenance hashes. Contract
17 is required by the changed window identifiers and source-target semantics;
its immutable baseline, migration, persistence/replay versions and generated client
are included. Historical baselines and neighboring roadmap orders remain separate.

The final attached-group audit found a component-bound movement-grant protection
that needed `rules_unit_persisting_effects`. The shared target-scope query now uses
that existing owner; regression cases cover both component-bound Overwatch
protection and canonical generic range restrictions before and after selection.
An in-progress coverage run was interrupted for this production fix and is not
claimed as a validation result. The final gates below cover the resulting build.

The broad suite exposed two stale expectations and an unnecessary eager-visibility
query introduced during implementation. The source-identity test now pins the
regenerated package hash. Returning optional window discovery to the existing
proposal contract also preserves the Cavalcade placement checkpoint and lets the
exact Event Companion ruin traversal reach its optional Overwatch decision without
solving unselected shots. The stalled prototype returned a typed interrupted
calculation error when its test worker was stopped; no visibility result was
invented. The diagnostic is retained with the performance evidence. The selected
shooter and every submitted shot still require exact current validation before
CP spend or authoritative mutation.

The full-suite follow-up also identified fixtures that assumed a stationary
enemy could not open Overwatch or that Rapid Ingress could never introduce a
shooter for the same phase-end batch. Those fixtures now explicitly decline the
newly valid opportunity through the shared session facade. No-target, destroyed,
embarked and reserve-only fixtures use the shared discovery eligibility checks.

The final quality audit now follows the extracted state-backed shooter keyword
authority and pins Snap's completed source status while preserving Indirect's
partial status. The existing Rapid Ingress benchmark explicitly declines the
newly valid post-arrival Overwatch window. Discovery reuses its current enumerated
rules-unit views instead of resolving every reserve unit again; the shared
submitted-shooter path still resolves its ID from current state. Existing Order 35
work budgets remain unchanged.

## Initial Order 45 validation

Final runtime build:
`warhammer40k-core-v2:runtime-tree-sha256-v1:f6a3f25877be161bc188e1e3c52a6bbf4187f529645b8084f56c04607671eef1`.

- Complete behavioral suite with coverage: **7,826 passed**, **85.09%** coverage,
  529.01 seconds; 18 xdist work-stealing workers. Ten SQLite ResourceWarnings were
  emitted; there were no failures or skips.
- Complete code-quality suite without coverage: **462 passed**, 101.71 seconds;
  18 xdist work-stealing workers.
- Ruff check/format, mypy (2,988 source files), Pyright, all 11 import contracts
  and `uv run pre-commit run --all-files` passed.
- Reviewed Stratagem source generation and external contract regeneration against
  base `a178a9e1ff5cac93c0c79e61499b2ce45f402012` passed.
- Installed-wheel smoke validated 2,778 runtime resources, 27 schemas and all six
  request families. TypeScript generated-client/type checks, five unit tests and
  all 342 live conformance assertions passed. Dependencies were installed with
  `npm ci` from the committed lockfile.
- All eight shard manifests and durations were regenerated from the complete
  successful JUnit profile above; the exact eight-shard fail-closed check passed.
- Matched Overwatch, exact-ruin/reserve and all five Rapid Ingress workloads passed
  their recorded budgets. Existing Order 35 budgets were not changed. Full-game
  performance remains uncertified.

The final behavioral suite ran with coverage, followed by the code-quality suite
without coverage. Earlier failed or interrupted runs are diagnostics only.

## R45-001: attached attacking range

The violated invariant is that Snap's 24-inch selection limit measures the full
rules unit, independently of the physical component owning the firing weapon.
The bug-class search found the same physical-unit argument in shooter eligibility,
candidate generation and declaration validation. All three now pass the current
`RulesUnitView` to the shared Snap helper, which considers every component with
present models. Existing per-weapon range, model visibility and present-target
measurement retain their existing owners. No wider geometry API or solver change
is needed. Obsolete component arguments were removed from the affected helpers.

Real facade regressions reproduce an unarmed Leader at 23.51 inches with the
firing Bodyguard at 25.66 inches. The Leader can supply unit range while the
Bodyguard supplies the only legal shot. Additional cases cover 23.999, 24.000 and
24.001 inches, a 24-inch firing weapon, blocked firing-model visibility, a removed
Leader, rejected-submission state equality, restore and exact boundary replay.
The static audit requires rules-unit scope at all three callers and current
presence filtering inside the shared range helper.

The existing contract already requires full rules-unit range; its wording now
makes attached-component scope explicit. No new decision shape, source text,
source-package identity or contract major is required. Runtime identity and its
contract examples were regenerated. The attached performance sample reuses the
existing versioned Overwatch limits without changing thresholds; see the paired
`r45-001` evidence in `docs/performance/order45/`.

The first aggregate run found one older retained-target regression calling the
private range helper dynamically with its previous physical-unit argument. Its
fixture now resolves a real `RulesUnitView`; the retained-target geometry and
living-only allocation assertions are unchanged. The corrected test and related
static audit pass. That failed run is diagnostic evidence only; the final
validation below covers the corrected fixture.

## R45-001 final validation

Runtime build:
`warhammer40k-core-v2:runtime-tree-sha256-v1:7850f542e6f905ae63908c3929b9b6239fd2df4b9974e18eef3e8c3b79203101`.

- Complete behavioral suite with coverage: **7,833 passed**, **85.09%** coverage,
  551.70 seconds; 18 xdist work-stealing workers. SQLite ResourceWarnings were
  non-failing; no tests failed or skipped.
- Complete code-quality suite without coverage: **464 passed**, 113.22 seconds;
  18 xdist work-stealing workers, after the passing behavioral suite.
- Ruff check/format, mypy (2,988 source files), Pyright, all 11 import contracts
  and `uv run pre-commit run --all-files` passed.
- The exact eight-shard fail-closed inventory check passed. The new regression
  cases extend an existing test file; test-file membership is unchanged.
- Engine identity, reviewed Stratagem source artifacts and generated external
  contracts passed their checks. Contract compatibility passed against unchanged
  base `a178a9e1ff5cac93c0c79e61499b2ce45f402012`.
- Installed-wheel smoke validated 2,778 runtime resources, 27 schemas and all six
  request families. TypeScript generated-client/type checks, five unit tests and
  all 342 live conformance assertions passed after `npm ci`.
- The paired attached-unit benchmark passed the unchanged Overwatch limits:
  0.0440-second base mean and 0.0427-second head mean, with four decisions and
  49 events in every sample. Full-game performance remains uncertified.
