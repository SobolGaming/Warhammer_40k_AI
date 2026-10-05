# Order126 / P03G / C03-07: sequential physical model movement

The retained Core `rule:03:03.01:1`, obligation03, block2 requires moving
models one at a time. The exact retained source and pinned diagnostic are
authenticated in `data/source_audits/order126/source.audit.json`. The original
Order97 sources, assertions and diagnostic remain immutable. This is an engine
consumer repair; it makes no official provider defect claim.

Previously each model's path was checked against every moving model's final
position. Two models could therefore exchange occupied starting positions even
though neither complete model move could finish first. `PathWitness` also sorted
submitted model paths, discarding the physical order chosen by the player.

The existing `model_paths` array now retains its submitted order. Each member
contains the complete straight/rotating/multisegment path for one physical model;
stationary members retain complete two-pose witnesses. The shared
`sequential_movement.sequential_friendly_models` owner uses final poses for earlier
members and starting poses for later members. Unmoving friendly models and
retained physical blockers remain at their current placements. Existing movement
permissions still determine which friendly models may be crossed in transit;
every intermediate completed endpoint must be clear of other physical models.

Ordinary Normal Move, Advance and Fall Back, attached component consumers,
Scout, Charge, Pile In/Consolidate and catalog-triggered movement share this
occupancy authority. Component validation retains the complete rules-unit witness
to preserve interleaved component order. Existing whole-group final coherency,
terrain, engagement, movement budgets and invalid-proposal atomicity remain
mandatory. Setup, ingress, disembark and teleport placement retain their distinct
placement authority.

The submitted order travels in the existing parameterized proposal, decision
record and completion witness, and is retained through normal JSON persistence,
forks, viewer projections/event streams and exact replay. Contract44.3.12
documents the existing payload's order semantics; runtime identity is regenerated.
No independent adapter mutation or new named handler is introduced.

Acceptance covers both cyclic orders, a legal vacate-before-follow order and its
invalid reversal, ordinary and attached facade submission/retry, stationary
members, multisegment paths/rotation, legal friendly transit, initial/pending and
completed save/load, fork isolation, both players and supported role viewers,
events and replay. Shared-consumer positive and negative controls supplement
the unchanged original behavioral suite.

Required delivery retains the complete covered inventory at 85% combined branch
coverage, current twelve shards, final quality/type/lint/import/contract/package
gates, quiet current-runtime smoke, native hosted CI, both independent final
exact-head reviews and protected squash publication. The bounded source repair
does not optimize algorithms or certify full-game performance. Speculative
coordinated hand-edited-history hardening remains separate under
`SEQUENTIAL_REMEDIATION_REVIEW_POLICY.md`. Stop after the Order127 handoff.
