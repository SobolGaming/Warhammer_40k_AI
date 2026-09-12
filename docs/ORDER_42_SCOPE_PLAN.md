# Order 42 — shared target invalidation and replacement

P04 / C04-01, developed against `b3186efa6de212f98f146d0e2099ebffbf622fa5`
and merged with main `58905502` before PR publication. The latter adds only
faction status documentation; the runtime identity is unchanged by that merge.

## Invariant and source

A target must have been eligible at its original selection. If it becomes
ineligible, only the controlling player's new validated decision may replace it.
The engine preserves the action, physical weapon/model identities, resolved dice,
completed attacks and source restrictions. Replacement does not grant an extra
attack, reroll, weapon use or movement allowance.

Section 04.03.03 was read directly in the expanded 40k.app browser section on
2026-09-12. Its short operative paragraph permits the controlling player to
select new targets when a previously eligible target becomes ineligible, giving
an out-of-phase move beyond range as an example. The approved Game Datamissions
mirror exposes the same paragraph and its v931 Charge FAQ expressly refers to
04.03.03. Neither site is official GW evidence; the repository's maintained
App-data mirror policy governs those observations.

## Scope and owning path

The shared service owns a closed target-selection context, deterministic finite
replacement choices, explicit decline and complete current-context comparison.
Action owners retain eligibility queries, authoritative mutation and continuation.
Shooting must invoke the service before gathering attacks from an unresolved
weapon, including suspended and out-of-phase Shooting. A weapon whose attacks
have begun cannot have those attacks redirected. Replacements must rebuild
target-dependent range, sight and modifiers while preserving committed dice.

Charge can use the same target-set service with its own current maximum-distance
query. The roadmap assigns the complete later-modifier Charge consumer to Order
46 / C11-03. Order 43 owns critical-hit and Snap-hit semantics; the older adapter
contract sentence assigning declaration sequencing to Order 43 is stale.

The bug-class trace includes accepted declarations, individual physical weapons,
One Shot use records, random Attacks, range-dependent bonuses, target restrictions,
attached rules units, out-of-phase source constraints, gathered/used attack pools,
decision dispatch, checkpoints, replay and shared adapter redaction. Hit-roll
resolution and the Charge movement-budget repair remain with their existing owners.

## Implementation and audit

`engine/target_replacement.py` is action-neutral and accepts target sets from an
owning eligibility query. Its closed context and exact finite result comparison
are reused by the Shooting consumer and exercised against real Charge target
queries. `shooting_target_replacement.py` enumerates current legal plans;
`target_replacement_dispatch.py` registers the lifecycle preflight and engine
mutation. `shooting_target_replacement_authority.py` authenticates the accepted
physical weapon inventory, recorded choices, resulting pools and pending restore.
No generic lifecycle code branches on faction, rule display names or source text.

Normal and out-of-phase Shooting check before gathering and before applying a
pending resolution selection. The latter records an explicit interruption if a
target has become invalid. Snap plans preserve the single target; unavailable
weapons are explicitly forgone in the selected plan. Duplicate Anti choices are
finite variants with display labels. Firing Deck preserves cargo weapon identity
and the already-spent selection, without importing cargo-only ranged keyword
effects into the transport's borrowed weapon. The ownership audit compared both
native and Firing Deck weapon builders; a real cargo Ignores Cover effect
regression failed before the correction and passes afterward.
One Shot uses and random Attacks are never
consumed again. Fixed/range/target modifiers are rebuilt through the existing
validator; a changed random Attacks expression fails explicitly instead of
inventing a roll. The original Shooting mode, including mixed Indirect weapons,
and out-of-phase source target restrictions remain authoritative.

The new 04.03.03 package is versioned JSON with an eager typed loader and byte,
transcription, catalog and source-authority pins. Its observation audit preserves
provider non-affiliation, minute precision and the historical official source
hash. `tools/build_core_target_replacement_source.py --check` reproduces it
offline. Source load and execution statuses are recorded separately.

External contract 15.3 publishes the new finite family and regenerated examples.
The existing shared redaction module removes the internal commitment from every
viewer-visible request, option, record, event and status path. No separate UI,
headless, network or replay mutation path is added. The old contract sentence
assigning target sequencing to Order 43 is corrected.

The scope/diff audit retained only this source-backed lifecycle, its consumer,
identity/contract artifacts, regression/architecture tests and timing evidence.
The existing Charge movement budget, Fire Overwatch timing repair (Order 45),
critical-hit/Snap hit resolver (Order 43), and faction support remain separate.

## Validation

The focused replacement file has 25 passing regressions, including facade
submission, malformed/stale rejection without queue pop, pending restore,
exact replay, both players and a spectator, Firing Deck, One Shot, random Attacks,
out-of-phase Snap source restrictions and protection for gathered attacks.
Cache regressions compare cached/uncached answers through range and hidden
changes, movement, casualties, retained-presence cleanup, restore and independent
games, including identical typed absence errors.
Existing Indirect-fire regressions also pass with preserved declaration mode.

The retained component/small-slice assessment passes unchanged budgets; see
[workload, base/head evidence and limits](performance/order42/README.md).
Complete-game performance is not certified.

The quality audit identified redundant modifier and visibility work against the
existing Order 33/34 limits. Eligibility-only checks now omit attack modifier
rebuilding, and declaration validation reuses one complete pure geometry query.
The key covers every input, including nested source mappings; runtime restrictions
are evaluated separately. No budget is raised.

Final behavioral validation passes all 7,484 tests with 85.05% coverage in
577.57 seconds, using xdist work stealing and the required Node.js PATH. The
successful JUnit profile regenerates all eight shard manifests and
`durations.json`; the exact fail-closed shard check passes.

Ruff, formatting, mypy (2,970 files), pyright and all 11 import contracts pass.
Source generation and runtime identity are verified. Contract regeneration
matches merged main `58905502`; TypeScript checks, five client unit tests and all
342 conformance assertions pass. The installed-wheel smoke verifies 2,768 runtime
resources and 27 schemas against runtime identity
`84b0a9d3d5b7e305b8766394ec6a75c2ff84121f9b5a60fc395cafe62b3f23b8`.
Pre-commit passes without changing production code. The final complete
code-quality suite passes all 440 tests without coverage in 115.54 seconds,
including the unchanged Order 33/34 budgets and the Order 42 evidence gate.
