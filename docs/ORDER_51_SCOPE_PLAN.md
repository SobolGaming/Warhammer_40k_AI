# Order 51 — Take to the Skies (P21A / C21-01)

## Required invariant

Flight benefits require a committed choice for the current Normal, Advance,
Fall Back or Charge move. Advance and Charge choices precede their rolls.
The unit pays the two-inch distance penalty unless it has Hover; only FLY
models gain model/terrain transit and ignore vertical distance. Every model's
traveled distance remains authoritative through the entire turn for Heavy.

## Source and ownership

The retained official Core Rules PDF, page 71 (21.03), defines unit selection,
the distance penalty and model-specific permissions. Page 82 defines Heavy
(24.16) and Hover (24.17). The App-data 931 FAQ was observed directly at
[Game Datamissions](https://game-datamissions.com/11th/rules/changelog?v=931) on 2026-09-15 and requires
selection before Advance and Charge rolls. The 40k.app page was unavailable
behind its verification checkpoint; no successful fresh observation is claimed.

Movement retains its finite movement-mode choice. Charge composes a flight choice
with its existing finite unit/modifier selection. Shared geometry applies the
choice to each model; Charge arithmetic applies its distance penalty after the
modified roll. Shared movement completion owns persistent model-distance history,
which Heavy reads after the temporary Movement phase state is cleared.

The consumer audit includes ordinary Movement, attached and mixed units, ordinary
and Heroic Charges, setup-reactive Charge, triggered Normal moves, path retries,
Heavy, restoration, replay, source artifacts and adapter contracts. P23's retirement
of the legacy AIRCRAFT toggle remains separate. No named handler, content-specific
generic gate, fallback or separate adapter mutation is authorized by this order.

## Scope and architecture audit

The change stays within choice authority, per-model movement capabilities,
accepted-distance history and their source/adapter persistence contracts.
`take_to_the_skies` and `flight_decision_authority` share finite choice and
commitment validation. `model_movement_history` owns the turn ledger; the large
GameState/lifecycle modules only serialize, initialize and delegate. Reactive
option construction was extracted before extension. No dependency boundary,
semantic handler budget, unsupported content scope or legacy Aircraft state
machine changed.

The same-bug-class search covered Movement, Charge, Heroic, setup-reactive Charge,
reactive Normal moves and historical Charge endpoint validation. Charge's recorded
unit FLY flag uses the rules-unit union; physical permission checks use each
model's canonical keywords. Hover never removes the choice. Existing Charge tests
that assumed particular seeded rolls now use real generic modifiers for the
required success/failure window; dice and decision validation remain active.

## Validation

Focused regressions cover Normal/Advance/Fall Back choices, timing, Hover,
ordinary/Heroic and attached Charges, mixed-model flight, rejected drift before
queue pop, reactive retries, exact replay, restore and cumulative per-model
vertical distances across the Shooting boundary. Static checks protect Heavy's
independence from temporary MovementPhaseState and pin the source artifact.

| Consumer | Regression evidence |
| --- | --- |
| Normal, Advance, Fall Back | `tests/unit/test_order51_flight.py`: finite choices, pre-roll timing, Hover, accepted paths and exact replay |
| Charge and Heroic Intervention | Order 51 tests plus `tests/unit/test_charge_distance_continuation.py`: committed roll authority, source caps, attached models and historical vertical-distance proofs |
| Setup-reactive Charge | `tests/unit/test_phase17d_rule_execution.py`: selected/declined flight, invalid retry, accepted completion and persistent distance |
| Reactive Normal moves | Order 51 tests: original finite choice retained through rejected proposals, retries and restoration |
| Per-model Heavy allowance | Order 51 and shooting declaration tests: mixed FLY models, actual vertical path distances, cumulative turn distances, Shooting boundary and checkpoint tampering |
| Geometry and source authority | Movement legality/pathing regressions, pinned source artifact audit and generated-source classification |

Shared historical movement fixtures now derive typed distance witnesses from their
actual model paths. The phase-state fixture also records its finite Charge choice.
These fixture changes preserve the required authority instead of supplying missing
production fields through defaults.

## Final local validation — 2026-09-15

Validated runtime `93b487aaac21bce4373c755445c3a477ea9b780407ad18394ca0a67f4eb56bd3`
against base `dc043bf27baf51c02d8db1a177190ecd77ad3254`:

- Complete behavioral suite with coverage: **8,088 passed**, **85.11%** coverage
  (85% required), 555.74 seconds, 18 workers with work stealing.
- Complete code-quality suite without coverage: **493 passed**, 101.21 seconds.
- Ruff check/format, mypy, Pyright, all 11 import contracts and pre-commit passed.
- The exact eight-shard inventory check passed. R51-001 adds cases to an
  existing behavioral file; the committed file inventory is unchanged.
- Source generator and engine identity checks, exact-base contract compatibility,
  generated TypeScript client/type checks, five TypeScript unit tests,
  **342 live conformance assertions**, and installed-wheel smoke passed.
- The wheel contains 27 schemas and 2,811 runtime resources and validates all six
  request families. Contract 22, persistence 14 and replay 16 are co-versioned.

The bundled Node runtime executed the TypeScript package script equivalents;
`npm` is unavailable on this host. See the [machine-readable validation record](performance/order51/validation.json)
and [matched performance evidence](performance/order51/README.md). Both Charge
slices pass the unchanged budgets; complete-game performance remains uncertified.

## Review correction R51-001 — reactive flight distance penalty

Violated invariant: the distance reported for a committed flight choice must be
the same distance enforced on its witnessed path before engine mutation. At
`09aaa696`, the shared reactive resolver computed the adjusted allowance but
passed the unadjusted descriptor maximum into physical validation. A three-inch
path was therefore accepted against a reported two-inch limit.

The repair passes the existing adjusted `maximum_distance` to validation. The
bug-class search covered every `movement_distance_budget_inches` binding in the
engine: ordinary movement uses its computed per-model budget, Charge (including
Heroic and setup-reactive Charge) receives its resolved maximum, and fight/Scout
consumers use their resolved move allowances. No second instance was found.
Both finite reactive candidates and parameterized submissions share the repaired
resolver, so they retain one validation and mutation path.

The facade regression failed before the fix, then passed with rejection at three
inches, unchanged positions/history after rejection, restoration and a legal
two-inch retry. Declining flight and Hover retain three-inch acceptance. Accepted
path-budget evidence must equal the reported allowance. A static audit rejects
passing the raw descriptor maximum directly to path validation.

No adapter-visible shape, choice, visibility policy or schema changes; the existing
contract 22 flight/retry semantics cover this correction. Runtime identity and
its generated examples are refreshed. Matched reactive-path measurements and
the unchanged-budget audit are retained in the linked performance evidence.
