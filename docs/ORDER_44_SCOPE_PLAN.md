# Order 44: optional Lethal Hits

P24H / C24-08, based on main `0a54e432aa9517e79ef60ea129a14c747aef7ff1`.

## Invariant and authority

Each original critical hit with applicable Lethal Hits belongs to the attacking
player, who chooses automatic wounding or an ordinary wound roll through the
canonical finite decision path. Automatic wounds are never critical wounds.
Additional Sustained Hits do not inherit automatic wounding or this choice.

The complete 24.23 rule and Designer's Note were observed on
https://www.40k.app/rules/24-core-abilities on 2026-09-13 at 15:00:34 UTC.
The approved maintained App-data mirror policy applies; 40k.app is not affiliated
with Games Workshop. No App-data version or second-provider corroboration is
asserted. Historical official provenance remains preserved in the source audit.

## Owning path and scope

Structured weapon descriptors and the finalized engine-recorded Hit feed the
shared attack resolver. It emits a finite request bound to the attack, weapon,
target, actor and source. Prevalidation runs before queue pop; the recorded choice
then resumes the same resolver, including ordinary wound rerolls and Devastating
Wounds. Lifecycle restoration and replay authenticate the same pending context.
Shooting, Fight and reaction attacks use the shared dispatch and viewer policies.

The bug-class search found one unconditional Lethal Hits mutation in
`attack_sequence_dice_rerolls._roll_hit_and_wound`. Dice override trigger markers
and runtime ability grants only describe eligibility and do not auto-wound.
No new handler, generic hook family, content scope or architecture boundary is
required. Existing decision-family lists should consume the shared family.

## Acceptance and validation

Required evidence: both choices in Shooting/Fight, Lethal plus Devastating Wounds,
additional Sustained Hits, conditional target eligibility, ordinary/automatic
hits, deterministic JSON-safe finite records, invalid/stale/drifted submissions
without mutation, pending restore, exact replay and viewer projection/event parity.
The focused matrix covers both phase families and both choices, critical wounds,
Sustained Hits, target/Torrent gates, pending request drift, invalid results,
historical automatic-wound/choice corruption, exact persistence/replay and both
viewers. A real accepted Fire Overwatch Stratagem proposal exercises the
out-of-phase attacking owner and Snap Shooting restore/replay. The older attack
fixtures now submit the new finite choice through the lifecycle; two fixtures
also use canonical one-model rosters instead of removing living models' placements.

The scope/diff audit retains one small semantic owner, shared attack dispatch,
prevalidation and restore integration, one reviewed source package, and Contract
16.1's additive finite family. No neighboring roadmap order is included. The
contract generator records envelope conformance separately from the real
facade-driven gameplay tests, without claiming extra live conformance scenarios.

## Initial implementation validation (de17df8f)

- Complete behavioral suite: **7,719 passed**, **85.08% coverage**, 18 xdist
  workers with work stealing, Python 3.14.5 and bundled Node 24.19.0. The run
  took 694.14 seconds and retained ten SQLite resource warnings; no tests failed
  or were skipped. The behavioral suite was not repeated without coverage.
- Complete code-quality suite: **457 passed**, 18 xdist workers with work
  stealing and no coverage. An initial attempt found an outdated local-constant
  audit and a missing decision-catalog row. Those audit/documentation fixes
  required this quality rerun; the runtime and behavioral coverage were unchanged.
- Ruff check and format, mypy, Pyright, import-linter (11 contracts), and
  pre-commit: passed.
- The complete successful JUnit profile regenerated `durations.json` and all
  eight shard manifests; the exact fail-closed `--check --shard-count 8` passed.
- Reviewed source generator and runtime build identity checks: passed.
- Generated contract `--check --base-ref 0a54e432aa9517e79ef60ea129a14c747aef7ff1`
  and installed-wheel package/contract smoke: passed.
- TypeScript generated-client/type checks, five unit tests and live HTTP
  conformance (342 assertions, Contract 16.1): passed.

The five matched performance workloads pass their fixed budgets with all samples
retained. See [measurements and workload limits](performance/order44/README.md).
Complete-game performance remains uncertified. The initial engine runtime identity
is `29f3f0ce86f4b093d94c0d90b161414bd0329bbcd0a2f85d4a50e946853d1652`.

## R44-001: historical choice authority

The violated invariant is that every accepted Lethal Hits answer, including a
decline, must retain its issued request and recorded decision before a checkpoint
can restore. Absence of an answer cannot mean an ordinary wound roll. A wound's
Command Re-roll window can pause before a Wound event exists, so wound-event
consistency alone cannot establish that the choice was answered.

The scoped repair authenticates the complete historical request and answer against
`decision_requested` and `decision_recorded` evidence, accounts for every issued
Lethal Hits request as answered or currently pending, and binds their ordering to
the existing recorded Hit and Wound context. Historical target metadata comes from
the issued request rather than re-evaluating a target that may since have changed.
The existing shared Hit authority still validates the recorded roll and source.

The bug-class search covers missing declines in completed Shooting/Fight histories,
changed target metadata and decision copies, missing journal evidence, and reordered
hit/request/answer evidence. The fix remains in the shared Lethal Hits history
validator used by restoration and attack prevalidation. It does not redesign the
general DecisionController journal or alter the adapter's finite payload shape.
Real Shooting and Fight controls exercise decline, wound Command Re-roll,
persistence and resumed completion. The focused matrix now contains 98 cases,
including 48 regressions for this repair. No behavioral test file was added,
removed or renamed; the existing shard inventory remains complete.

### Repair validation

- Complete behavioral suite: **7,767 passed**, **85.08% coverage**, 18 xdist
  workers with work stealing, Python 3.14.5 and bundled Node 24.19.0. The run
  took 557.63 seconds and retained ten SQLite resource warnings; no tests failed
  or were skipped. The behavioral suite ran once with coverage.
- Complete code-quality suite: **458 passed** in 104.71 seconds, 18 xdist
  workers with work stealing and no coverage, run once after the behavioral suite.
- Ruff check and format, mypy (2,984 files), Pyright, import-linter (11 contracts),
  pre-commit and the exact eight-shard inventory check: passed.
- Source generator and final runtime build identity checks: passed.
- Generated contract compatibility against base
  `0a54e432aa9517e79ef60ea129a14c747aef7ff1` and installed-wheel smoke: passed.
- TypeScript generated-client/type checks, five unit tests and 342 live HTTP
  conformance assertions for Contract 16.1: passed.
- Seven matched samples per phase pass the fixed restore and continuation
  budgets with identical decision and event counts. These are component
  measurements; complete-game performance remains uncertified.

The repaired runtime identity is
`warhammer40k-core-v2:runtime-tree-sha256-v1:a9501dcb68ef021c48d21b10bd17fe4ee6c1ab5ae1e91f052e26bee2228e8031`.
