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

## Final validation

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
Complete-game performance remains uncertified. The final engine runtime identity
is `29f3f0ce86f4b093d94c0d90b161414bd0329bbcd0a2f85d4a50e946853d1652`.
