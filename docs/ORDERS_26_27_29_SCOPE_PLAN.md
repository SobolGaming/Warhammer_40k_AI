# Orders 26, 27 and 29

The owner requests one PR for P02A/C02-01, P02B/C02-02 and P02C/C02-03.
Base: `55c06d4dad60c34a77b381d864db7e7d1c3f98a8` (Order 25 merged).

Invariant: modifiers use replacement, multiplication, addition, division and
subtraction in that order, with exact intermediate arithmetic and one final
rounding step. Characteristic replacements of 0, dash and star are terminal.
Dice preserve their original and rerolled faces separately from modifications
and domain limits. Modified results have a minimum of 1; Charge results have a
maximum of 12. Detection and Lone Operative ranges end within 9–30 inches.

The core modifier service owns arithmetic and limits. Existing typed runtime
descriptors supply operations and source IDs. Dice records own faces/rerolls;
engine result records own modified results and downstream movement budgets.
Shooting targeting consumes the shared terminal range policy after all local
source effects have been collected. State mutation, decision submission,
events, adapters and replay retain their existing owners.

The consumer audit includes characteristic and Damage resolution, Battle-shock,
hit/wound/save results, Advance, Desperate Escape, ordinary Charge and Heroic
Intervention, Hidden detection and Lone Operative selection. Source metadata,
serialization, restoration, external contracts and build identity are part of
the same invariant. Frozen large modules require extraction before extension.

Order 28's individual Psychic modifier choices, Order 43's target replacement
and Charge declaration semantics, and later Command Re-roll/Into the Fray
orchestration remain their scheduled work. This PR does not certify all of
category 02 or add faction content. Required numeric Charge result limits must
still reach existing Charge consumers; they cannot be deferred with Order 43.

Before publication: failing focused regressions, real-domain consumer/facade
and replay tests, static bug-class checks, scope/diff audit, final behavioral
coverage run, code-quality suite, type/lint/import gates, generators, eight-shard
inventory, external base-ref compatibility, TypeScript/conformance and wheel smoke.


Scope audit completed before aggregate gates: substantive changes are confined
to the modifier/result owners and their consumers. Other production-file changes
are import/extraction wiring or immutable source/contract/build artifacts. No
architecture boundary, mutation authority, decision family or named-handler
budget changes. The same-bug search found random Damage raw-record corruption
and terminal-zero loss during Damage conversion; both are required instances
of the selected invariant and have direct regressions. Private Advance helpers
are removed from the old phase facade's export inventory after extraction.

The aggregate iteration found stale test expectations (source count, raw Advance/
Charge expressions, minimum-one saves and the contract version), coordinated
forgeries that needed the new roll-stage fields, and fixed-seed scenarios whose
later outcomes changed because DiceRollManager hashes event history. Those
fixtures retain their gameplay assertions and use recorded fixed seeds that
reach the same intended decisions. RNG history and production behavior are not
weakened to preserve outcomes from the former event schema. All such changes
are in existing tests and will be covered by the final complete coverage run.

The final conversion audit also closes terminal-zero metadata loss through
`BoundedCharacteristicValue` JSON/conversion. A direct regression covers that
path and rejects malformed symbolic/nonzero replacement records.

## PR #432 review correction: cumulative runtime characteristics

Reviewed commit: `e5aba9edf8ab603523ff3d5a52c09e95cad4608b`. Its remote
[CI run #1555](https://github.com/SobolGaming/Warhammer_40k_AI/actions/runs/34082116967)
completed successfully. Those results describe the reviewed commit, not the
correction, whose final validation is recorded below after revalidation.

The real-domain regression in `tests/integration/test_core_modifier_boundaries.py`
now exercises base Toughness 6 with independently sourced -8 and +4 effects,
swapped source order, both direct registry and attack Toughness consumption,
JSON state restoration, and a duplicate occurrence of the negative source slot.
The existing selection deduplicates that slot correctly. Before production edits,
the eight-case focused run has four failures and four passes: every negative-first
case returns 4 instead of the required 2, including restored attack consumption.

The violated invariant is cumulative characteristic resolution: collect applicable
source-linked operations, apply the core ordering, then apply the characteristic
bound once. A producer's source ID must not determine the numeric result.

The source-to-consumer trace is retained generic RuleIR effect payloads →
rules-unit effect applications → `generic_rule_matching_unit_effects` source-slot
deduplication → generic characteristic deltas → registered/generic runtime
resolution → attack Toughness or the other characteristic consumer. State
restoration preserves all three original effect occurrences and reproduces the
same two applicable source slots.

The same-class audit found the following additional boundaries requiring review
as part of a complete correction:

- `RuntimeModifierRegistry.modified_unit_characteristic` composes resolved
  integers and rejects negative intermediate values. It cannot preserve an
  operation that a registered producer has already rounded or clamped.
- Death Guard's registered Toughness provider delegates to a helper that applies
  `max(1, base_toughness - 1)`. Imperial Knights' registered Leadership provider
  applies `max(1, current_value - 1)`. Astra Militarum's registered Save and
  Leadership providers use source-specific improvement caps. Their source-defined
  limits must be preserved explicitly, rather than simply deleting every bound.
- The catalog's unit-characteristic providers include both signed deltas and
  replacements. Treating every registered integer result as a delta would lose
  replacement semantics and would not establish the shared operation invariant.
- `generic_rule_objective_control_trace` repeats the per-effect zero clamp over
  the same characteristic-delta query.
- `generic_rule_movement_modifier_trace` also clamps each characteristic delta,
  then each separate move-distance effect. Its application records require
  nonnegative before/after values, so simply allowing negative intermediate
  values would violate the existing trace contract. Characteristic operations
  and later movement-distance effects need their proper separate boundaries.
- Historical Leadership providers have their own reconstruction path and some
  equivalent caps; changing live characteristic semantics requires checking that
  historical validation still reconstructs the same authoritative result.

Proposed expanded correction: have registered characteristic producers supply
typed source-linked operations to the existing core arithmetic owner; combine
them with deduplicated generic operations before terminal bounds. Migrate the
Objective Control and movement characteristic consumers without conflating
subsequent move-distance effects or source-specific limits, preserve historical
validation, and update trace contracts only where the resulting payload changes.
Add real consumer/restoration regressions and a static audit for these owners,
then regenerate runtime identity and contract artifacts, rerun the required full
gates, and update the existing PR.

The owner approved this expanded correction with “Approved, fix”. Registered
characteristic producers now return typed operations; the shared core orders
them alongside deduplicated generic operations before bounding. Catalog
replacements remain replacements. Death Guard and Infamy OC minimums and Take
Cover's source-specific Save limit remain explicit floor operations. Historical
registered Leadership producers supply the same operations to the authenticated
event-bound validation path. Numeric consumers reject symbolic replacements.

Movement carries the typed source characteristic through its engine context,
preserving terminal replacements. Internal arithmetic traces permit negative
intermediate values. Characteristic resolution precedes separate cumulative
move-distance resolution, which retains fractional inches. Both traces retain
source IDs; OC checkpoints collapse internal operation IDs to their original
registered binding IDs so source authority remains exact.
The terrain inventory's structural OC check now permits replacement base/value
kinds with added source identity. Its separate authenticated runtime checkpoint
reconstruction still compares every result field exactly; terminal source values
must remain identical. The existing increase-from-zero and replacement-zero
scoring regressions exercise this boundary.

The regression set extends the original failing Toughness scenario to attached
units, real registered contagion combined with generic effects, Objective
Control consumers/checkpoints, movement distance separation, terminal values,
negative trace intermediates, source provenance and JSON restoration. Existing
catalog proximity Leadership replacements retain live/historical parity.
Source providers' standalone single-effect helpers are not intermediate runtime
folds; registered paths no longer delegate to their local clamps. The static
audit checks the cumulative owners and typed producer return surfaces.

The corrected Leadership maximum of 9 changes fixtures that previously relied
on Leadership 13 to force failed tests. Five deterministic fixture-ID families
were refreshed after executing their complete original scenario assertions,
including both phase-start variants and pending/completed restoration tamper
cases. This changes neither RNG history semantics nor failure/replay assertions.

The first aggregate correction run reached 85.05% coverage with 6,528 passes and
seven fixture failures. Two remaining consumer assertions expected Leadership
2/3 instead of the minimum 4. The other five cases relied on out-of-range
Leadership to force Daemonic Terror/Delirium outcomes. Their complete original
scenario assertions select deterministic fixture IDs under the corrected
maximum; the Fall Back cases retain Feel No Pain, embark, destruction and replay
checks. No production code changed in response to that run. Final successful
aggregate evidence supersedes those iteration results below.

Pre-aggregate scope/architecture audit: the added abstraction binds source-linked
operations and resolves runtime characteristics. No new hook family, named
handler, content rule, package boundary, decision or visibility class is added.
The movement context change is internal; the adapter contract documents the
trace meaning and retained source identities without adding a public schema.

## Validation at 441631a6

Validation results: the final complete behavioral suite passes with coverage:
`6535 passed`, `85.08%`, `744.10s`, 64 xdist workers with work stealing and the
bundled Node runtime on PATH. The run reports 10 existing SQLite connection
ResourceWarnings. The first aggregate iteration's seven fixture cases pass
their focused regressions before this successful full run.

The subsequent complete code-quality suite passes once without coverage:
`388 passed`, `305.07s`, 64 xdist workers with work stealing.

Ruff check, Ruff format check (2833 files), mypy (2743 source files), pyright
(zero errors/warnings), all 11 import-linter contracts, and all-files pre-commit
pass. The exact eight-shard inventory check passes; this correction adds no
behavioral test file. The source/audit builder and runtime build-identity checks
pass. Engine identity:
`warhammer40k-core-v2:runtime-tree-sha256-v1:a10ca235c1b439bdec1ab473ba347953e49fbb7052dcdee037f45eb4af872224`.

External-contract `--check --base-ref origin/main` passes against
`55c06d4dad60c34a77b381d864db7e7d1c3f98a8`. TypeScript generated-client/type checks,
all five client unit tests, and two-server HTTP conformance pass (342 assertions,
contract 11.4.0). Installed-wheel smoke verifies 2572 runtime resources, 27 schemas
and six request families against the same engine identity. Scope, architecture,
module-size and diff audits pass. No production code changed after the aggregate
coverage runs began.

## Historical generic Leadership follow-up

Review of 441631a6 identified a remaining operation-inventory mismatch: live
Battle-shock included generic Leadership effects, while historical request
authentication included only registered providers. The focused regression
reproduced base Leadership 6 plus generic +1 recording 7, then failing unchanged
restoration with `Battle-shock request Leadership lacks exact authority`.

The correction reconstructs generic effects from causal events before the
original test boundary. Loaded source RuleIR authenticates the clause, effect
slot, semantics, target, duration and source identity. Immutable army and
rules-unit membership authenticate ownership; optional activations retain their
exact decision/event closure. Creation clocks come from phase history, expiration
comes from the loaded duration and original turn order, and attack completion
uses its existing expiration selector and completion-event anchor. Installation
records use the same detachment/Enhancement validators as OC authority. Recorded
effect copies must agree with the reconstructed source execution.

Live and historical paths share rules-unit lineage/Aura applicability, generic
source-slot deduplication and characteristic-operation construction. Both generic
and registered historical operations enter the same ModifierStack before the
unchanged exact request comparison. No restored current-effect inventory is used
as historical evidence. The duration evaluator now declares the read-only
calendar interface it consumes; no partial GameState or fallback is introduced.

The bug-class search found existing OC source validation and generic effect
matching with the necessary semantics. Those owners were extracted and reused
instead of duplicating source validation or modifier selection. Existing OC
authority regressions remain in place. New regressions complete Battle-shock
through LocalGameSession, check generic-only and registered-plus-generic values,
activate duplicate source occurrences through normal decisions, and require exact
lifecycle/session restoration and replay, including after phase expiry. Tampered
delta, target, source, duration, creation clock and activation evidence fail
closed. An expiration-boundary matrix and a static shared-path/current-effect
audit cover the changed invariant directly.

Pre-aggregate scope/architecture audit: this follow-up changes historical effect
inventory reconstruction and extracts existing source/applicability code. It adds
no rule content, hook family, named handler, decision, public payload shape,
visibility class or package boundary. The adapter contract remains 11.4.0. New
production modules remain below 1,500 lines. Existing behavioral test files are
extended, so the eight-shard inventory is unchanged.

Final historical Leadership validation:

The complete behavioral suite passes once with coverage: `6564 passed`,
`85.06%`, `795.05s`, 64 xdist workers with work stealing and the bundled
Node runtime on PATH. The 10 warnings are existing SQLite connection
ResourceWarnings. The subsequent complete code-quality suite passes once without
coverage: `389 passed`, `347.53s`, also using 64 workers with work stealing.

Ruff check, Ruff format check (2836 files), mypy (2746 source files), pyright
(zero errors/warnings), all 11 import-linter contracts and all-files pre-commit
pass. The exact eight-shard inventory check passes. The source/audit artifact
check and runtime build-identity check pass. Engine identity:
`warhammer40k-core-v2:runtime-tree-sha256-v1:a88ba836f139acb5f7c74451b1939927f3084d60b6ae85dd53bd23002a01128b`.

External-contract `--check --base-ref origin/main` passes against
`55c06d4dad60c34a77b381d864db7e7d1c3f98a8`. TypeScript generated-client/type
checks, all five client unit tests and two-server HTTP conformance pass
(342 assertions, contract 11.4.0). Installed-wheel smoke verifies 2574 runtime
resources, 27 schemas and six request families against that engine identity.
Scope, architecture, module-size and diff audits pass. No production code changed
after the aggregate coverage run began.
