# Order 50 — Heroic Intervention (P15C / C15-03)

## Invariant and source

Heroic Intervention resolves an ordinary Charge through the same declaration,
reroll, modifier, target commitment, replacement, witnessed movement, completion
and replay owners. Its source supplies restrictions; it must not implement a
second Charge engine.

The retained official Core Rules PDF, page 57, 15.11, requires:

- End of the opponent's Charge phase; one friendly unengaged unit within 12 inches
  of an enemy. A VEHICLE must also be a CHARACTER or WALKER.
- Select the mode before rolling. Leap to Defend permits only enemies that made
  a Charge move this phase and are within the maximum distance.
- Into the Fray costs one additional CP, caps the Charge roll at six **after
  modifiers**, and permits enemies within six inches and the maximum distance.
- Resolve the Charge under 11.02, including its ordinary restrictions and bonus.

Official artifact: `docs/source_rules/eng_01-06_warhammer40k_new40k_core_rules-was6fbu1ix-hfewhmxyiy.pdf`,
SHA-256 `f6a2443a44627ac5f0ef08407d29aa5ec7e97339998f05bc35f3ae37bf276833`.
The local official artifact was inspected for this work; no successful fresh
maintained-mirror observation is claimed.

## Ownership and scope

The existing source-linked Stratagem provider hands one authorized unit and its
mode restrictions to a typed interrupted Charge sequence. The ordinary Charge
phase state is suspended and restored. Turn ownership remains unchanged.
The shared Charge owner handles all subsequent decisions and movement.
Into the Fray's roll limit is recorded separately from movement-distance
modifiers, which are applied after the limited roll. Leap target authority comes
from completed Charge history rather than a Fights First grant.

The bug-class audit includes ordinary and reactive Charge eligibility, attached
identities, target hooks, modifier-ignore/declaration choices, natural rerolls,
the one-Stratagem-per-unit restriction, stale proposals, move completion,
Fights First expiry, restoration, replay and generated contracts. Existing setup
reaction Charge behavior is outside the requested mode orchestration; shared
arithmetic and identity fixes apply to its existing consumers.

No new named content handler, generic registry, architecture boundary, or
adapter-specific mutation is required. The existing Heroic Intervention provider
retains responsibility for its source-specific mode selection and CP context.

## Architecture and bug-class audit

The final engine change removes the private Heroic roll, reroll and movement
continuations. Shared Charge eligibility and phase progression were extracted
from the existing over-budget module before extending them. The remaining
provider supplies the source restriction record; it does not roll dice or mutate
placements. Downstream geometry, objective, trigger and event consumers now
receive the same `charge_move_completed` event as ordinary Charges.

The actor/turn audit also corrected target ownership, Fights First expiration,
Charge-grant expiration and shared modifier-ignore expiration. Effect ownership
remains with the acting unit, while duration follows the current opponent turn.
Source history validates the exact recorded Stratagem use, modified roll limit,
actor, target restrictions and completion. No named handler or registry was added.

Leap uses the completed phase's successful-target map. An unrelated Fights First
effect cannot qualify a target. Selecting a mode without a legal Charge target
finishes the authorized sequence without rolling or moving, through ordinary
Charge eligibility. The already-used Stratagem retains its recorded cost.

## Validation

The PR review found a restore invariant violation: every supported decision emitted
by the shared Charge completion owner must remain valid while the interrupted
Charge holds its reaction frame. The restore allowlist omitted catalog mortal-wound
target selection and rules sequencing. Both now require the existing active
interruption context; all frame identity, phase and request checks remain intact.
The consumer audit traced completion sequencing, catalog target selection,
mortal-wound allocation, Feel No Pain, destruction, Battle-shock rerolls and
Stratagem continuations. The latter families were already allowed.

Regressions load one or two catalog mortal-wound abilities, complete a witnessed
Heroic Charge, restore each pending completion/damage checkpoint, and compare
continuation payloads and exact replay. They also reject completion types outside
an interrupted Charge. The canonical fixture now records turn-start evidence so
completion damage can destroy a unit through the ordinary scoring authority.
This repair changes only restore decision admissibility, with two fixed set
entries; gameplay algorithms, orchestration and existing performance budgets
are unchanged. The existing decision contract covers these finite choices.

Focused regressions cover source-loaded conditional grants and modifier-ignore
permissions, both natural-reroll choices, positive/negative roll modifiers,
post-cap movement effects, the six-inch target boundary, VEHICLE exceptions,
AIRCRAFT restrictions, attached actors, invalid/retried paths, stale submissions,
source-history drift, viewer projections, restoration and exact replay.

Final behavioral validation after the completion-checkpoint repair: **8,051 passed**,
**85.12% coverage**, 18 xdist workers with work stealing. The original successful
implementation profile regenerated all eight committed CI shards; this repair
adds cases to an existing inventoried file, and the exact shard check passes.
Coverage output used an isolated temporary directory. The original implementation
run identified nine obsolete contract/event fixture expectations, all corrected
before its successful complete rerun.

The complete code-quality gate passed **487 tests** without coverage. Two stale
static references to extracted/deleted functions were updated before its final
successful run. All-files pre-commit and the exact eight-shard check passed.

Ruff, mypy, Pyright, import boundaries, exact-base contract/build checks, installed
wheel smoke, TypeScript generated-client/type checks, five client unit tests and
342 live conformance assertions passed. Matched ordinary and Heroic Charge timing
evidence lives in `docs/performance/order50/`. Full-game performance certification
remains deferred and is not claimed.
