# Order 43: critical-hit success and Snap Shooting

P04B / C04-02 and C04-03, against main
`15856aca9550bf9296ebfbf74e165e889301e705`.

## Invariant and source

An unmodified hit roll meeting a source-backed critical threshold must be both
successful and critical, even when ordinary skill requires a higher value.
Hit modifiers do not change the raw face used for that threshold. Snap Shooting
requires an unmodified six unless the applicable source explicitly overrides
Snap; generic critical or hit-success thresholds do not supply that permission.

The two complete App-data v931 FAQ entries were observed in Game Datamissions
on 2026-09-13 at 00:36:53 UTC. The immutable package and observation audit retain
the FAQ text, transcription hashes, provider version and non-affiliation,
historical official source hash and separate load/execution status. The approved
maintained App-data mirror policy governs these Core Rules observations. No
second provider's co-versioned observation is asserted.

## Owning path and bounded change

Source text is compiled once by `hit_success_threshold_parser` into a distinct
`critical_hit_threshold` contextual status, preserving targeting-mode gates.
Versioned generated RuleIR supplies the engine's existing generic effect path.
`hit_thresholds.resolve_hit_thresholds` uses the existing model/rules-unit,
condition, phase and target matcher once. The shared `_roll_hit` consumes its
minimum, effective critical threshold and deterministic source IDs. Both critical
success and Sustained Hits use the resulting critical flag. Existing Lethal Hits
consumes that flag only for the original hit, not additional Sustained hits.
Automatic hits never invent a critical roll.

The existing Indirect Shooting failed-face floor bounds the critical threshold.
Explicit ordinary hit-success permission remains distinct from critical status.
The shared HitRoll validates raw/current dice agreement, the modifier trace,
failed-face floor and flags together, and serializes the effective threshold and
source IDs for restore and replay. The adapter decision contract must record the
new persisted fields; no new decision family or adapter-specific mutation is needed.

The bug-class search covered the compiler, all generated copies of its output,
ordinary/Snap/Overwatch/Indirect consumers, hit serialization, critical events,
Lethal Hits, fixed/D3 Sustained Hits and the shared runtime registry API. Target
replacement, Charge budgets and Fire Overwatch timing remain separately owned
roadmap items. This change does not certify every faction ability's activation
or full game semantics.

## Generated data and scope audit

Eleven existing Stratagem profiles compiled critical prose as ordinary hit
permission. Regenerating those consumers requires moving the existing generated
Python table to JSON under AGENTS.md. The typed eager loader preserves every
profile's source/selection metadata, validates exact profile/IR inventories and
source/hash identity, and performs one indexed validation pass. The generator
emits JSON and supports `--check`. The retained migration audit compares all
1,025 profiles against base: 1,014 IR payloads are unchanged, and eleven carry
only the intended critical descriptor change. Existing placeholder profiles
remain placeholders; the migration creates no gameplay-support claim.

The affected Aeldari and Court catalogs, per-effect coverage and human prose
fingerprints are regenerated in dependency order. The prose continues to describe
critical thresholds; its evidence now names the correct critical consumer.
No source-specific branches, named handlers, compatibility fallback, new content
scope, or architecture-boundary changes are introduced.

## Regression evidence

Focused tests cover all D6 faces with positive/negative capped modifiers for
ordinary, Snap, Overwatch and both Indirect floors; explicit Snap hit versus
critical permission; automatic hits; malformed thresholds; fixed/D3 Sustained
Hits; and corrupted hit/source records. Shooting activates the real generated
Targeting Override through the lifecycle-loaded Stratagem bundle. Fight uses a
canonical persisted threshold fixture with real melee weapons. Both resolve
through LocalGameSession decisions, restore at pending boundaries, preserve both
viewer projections, and reproduce exact replay and event streams.

## Approved contract migration

The owner approved contract 16 on 2026-09-13. Required nested hit fields
and changed critical evaluation are versioned with metadata/command families
v16, persistence v8-critical-hits and replay v10-critical-hits. Client artifacts
and one new compatibility baseline are regenerated; all previously released
baselines remain immutable. Old saves require their matching original deployment.
See `contracts/migrations/15-to-16.md`. No new player choice is introduced.

The new hit fields enter the existing canonical event history used by subsequent
RNG draws. Existing seeded leadership, Hazardous, reroll and nested-casualty
scenarios therefore use refreshed deterministic seeds. Their original outcomes,
branch assertions and replay checks remain intact; the RNG implementation and
history-neutral metadata policy are unchanged. The first aggregate run exposed
21 stale fixtures/assertions while reaching 85.04% coverage; it is retained as a
diagnostic and does not count as a passing final gate.

## Final validation and publication gates

Final local validation on 2026-09-13 UTC, against the unchanged base above:

- Complete behavioral suite: **7,653 passed**, **85.07% branch-aware coverage**,
  490.57 seconds, 18 xdist work-stealing workers with the required Node PATH.
  No second full behavioral run without coverage was used.
- Complete code-quality suite: **451 passed**, 100.11 seconds, 18 work-stealing
  workers without coverage. This includes the macOS generated semantic audit.
  Its initial stale 26-package assertion was corrected to include the new FAQ
  package before the passing final run.
- Ruff check/format, mypy, Pyright, all 11 import contracts and pre-commit pass.
- The eight-shard inventory is regenerated from the successful full local JUnit
  report, accurately labeled with the host, base commit and final runtime identity;
  the exact fail-closed eight-shard check passes.
- Source/activation generators, affected catalog and coverage artifacts, engine
  identity, and the external contract check against exact base
  `15856aca9550bf9296ebfbf74e165e889301e705` pass. Released baselines are unchanged.
- Generated TypeScript client checks, TypeScript compilation, five client unit
  tests and **342 live conformance assertions** pass on contract 16.0.0.
- Installed-wheel smoke passes with **2,772 runtime resources**, **27 schemas**
  and all six request families. The packaged runtime identity is
  `b1a8d5d1e8216f4842d66af0de630b512c6c437f757454566ab7769523624ffc`.
- The retained base/head component and shooting-slice measurements pass their
  fixed budgets. Complete-game performance remains uncertified; see
  [the performance record](performance/order43/README.md).

The final passing behavioral run includes every refreshed gameplay fixture.
Subsequent edits only correct the quality inventory assertion and update shard
inventory/documentation. No production change follows the final behavioral gate;
the generated runtime identity, contract conformance and measured implementation
remain the finalized contract 16 version described above.
