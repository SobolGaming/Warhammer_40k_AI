# Order 46 — Charge movement budgets and target continuation

## Required invariant and ownership

C11-01/C11-03 require three distinct values: the original 2D6, the current
modified Charge result bounded to 1–12, and the movement maximum after subsequent
move-distance effects. A target must be within both that maximum and 12 inches.
If a later change invalidates committed targets, the controlling player must
resolve the shared P04 replacement choice before a Charge move can mutate state.

Orders 26/27 already supplied raw dice and bounded modified-roll values. This
change preserves those owners and corrects the consumers that treated the roll
as the entire movement budget. Generic modifier services own current source-linked
roll and move-distance effects. Charge owns reachability, required-target
constraints, committed targets, and continuation; P04 owns replacement decisions.
Shared dispatch and restore bind each request to its active action ID, preserving
Shooting ownership when an out-of-phase attack interrupts Charge.
The physical movement validator still requires a complete `PathWitness`.

## Source and execution path

The maintained 40k App Charge page (11.02/11.04) and App-data changelog version
931 were observed through the browser on 2026-09-14. The FAQ explicitly applies
modifiers before target selection and refers later invalidation to 04.03.03.
The reviewed FAQ transcription is committed as JSON in
`rules/source_packages/warhammer_40000_11th/core_charge_2026_09`, with a typed
loader, source hashes, audit artifact, registry authorization and reproducible
`tools/build_core_charge_source.py` generator. These are maintained mirror
observations under the repository's approved source-authority policy, not new
official GW evidence. The audit retains the existing official GW provenance.

The authoritative path is charging-unit decision → source-backed declaration
grant/reroll → original roll and budget → finite target-set choice → current
budget/target revalidation → P04 replacement when necessary → parameterized
Charge path → engine-owned validation/mutation → decision/event/replay history.
Stale submissions preserve state and queue. Advancing withdraws stale target or
movement authority and issues a fresh request without rerolling. Source-required
targets remain mandatory; they are not silently dropped from a target set.

The same bug-class search covered setup-reactive Charge. Its existing fixed
target context now consumes the shared bounded-roll and movement-budget resolver
and rejects changed budgets before mutation. This does not add a new reactive
target-selection family.

## Architecture and scope audit

Charge state/value objects and proposal flow were extracted from the existing
oversized Charge phase module before extending their responsibilities. The new
budget, continuation, dispatch, and restore-authority modules remain below the
module-size limit. Large legacy Charge test fixtures were moved into named shared
helpers, with all test consumers using the lifecycle decision path. No named
content handler, generic hook family, dependency-boundary change, or adapter
mutation path is introduced.

The adapter contract advances to major 18 because persisted Charge state and
proposal source context acquire required authority fields. Public finite choices
use deterministic option IDs; shared redaction removes internal context hashes
from both projections and event deltas. Restored movement authenticates the
original roll, target commitment, replacement decision and causal event history.

Per-model Charge endpoint optimization remains Order 47. Command Re-roll timing
remains Order 49, Heroic Intervention's ordinary-Charge integration remains
Order 50, and the Take to the Skies choice remains Order 51. Order 46 implements
the distance-effect surface consumed by that later choice without prebuilding it.

## Validation

Focused real-domain regressions cover cap ordering, zero/fractional/above-12
movement budgets, exact source modifier terms, current modifier reevaluation,
finite target commitment, stale requests, later roll/distance changes,
replacement/decline, path-target binding, required targets, attached rules units,
checkpoint tampering, replay and viewer-scoped projections. Static audits cover
source generation and shared mutation-owner wiring. The final validation record
is reported with the PR; performance evidence is retained in
[`performance/order46`](performance/order46/README.md) and does not certify a
complete headless game.
