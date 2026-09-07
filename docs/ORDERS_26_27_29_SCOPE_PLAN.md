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
