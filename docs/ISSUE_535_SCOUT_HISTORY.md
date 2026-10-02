# Issue 535: Scout physical history

## Invariant and owner

An accepted engine-owned physical move must appear exactly once, in event order,
in the shared battlefield history used by checkpoint restore, fork and replay.
This includes every physical component of an attached rules unit.

The public path is `LocalGameSession.submit_parameterized_payload` through the
pre-battle decision validator and `scout_movement.apply_scout_move`. The engine
atomically replaces component placements, records the pre-battle action, and
emits `prebattle_scout_move_completed`. Its existing physical batch lives at
`resolution.transition_batch`.

`battlefield_transition_history.authoritative_battlefield_transition_batch_or_none`
owns extraction for the forward physical-authority reconstruction and reverse
Fight model timeline, plus Charge and base-contact consumers. The missing Scout
family and nested path caused legal nonzero moves to disappear from reconstruction.
The repair belongs in that shared extractor; consumers keep their existing order
and once-only handling. Scout completions require an object resolution and batch;
other event families retain their existing top-level shape and optional-batch
semantics.

## Scope and contract

The existing Phase 16B [adapter contract](ADAPTER_DECISION_CONTRACT.md) covers the
Scout proposal, completion event, displacement batch, public visibility, and
restore/replay obligations. No decision, event payload, proposal, schema version,
visibility rule or runtime mutation path changes. Generated runtime identity and
external examples must be refreshed by the ordinary build workflow.

The omitted-family search checked transition producers and all shared extractor
consumers. Fight completion already carries its authoritative batch at top level;
Fall Back and Embark retain their specialized once-only handling. Redeploy and
Scout reserve setup also emit nested pre-battle resolutions, but their normal-play
restore behavior is not established by this repair. They remain separate work;
this change does not expand their support or certify them. Coordinated manual
history edits remain outside this bounded legal-state repair under the
[sequential review policy](SEQUENTIAL_REMEDIATION_REVIEW_POLICY.md).

## Regression coverage

The existing setup facade suite exercises both players' ordinary and attached
Scouts, including nonzero and zero-distance moves, JSON persistence restoration,
independent fork continuation, exact replay, and both viewers' projections.
Rejected witnessed proposals preserve the pending request and state before a legal
retry. A fork can skip the second player's Scout without consuming the source
session's choice. Focused parser tests preserve registered top-level families,
optional/nonphysical controls and typed malformed-payload errors. The existing
shared-registry architecture audit also binds Scout's emitted event to the registry.

No new behavioral file is added. Full correctness, generated-artifact, contract,
type, quality and serial live performance gates remain required on the final head;
focused evidence alone is not the final validation certificate.
