# Issue 534: reserve deadline model state

## Invariant and authority

Destroying unarrived reserves must leave live army models, reserve status,
Transport cargo, battlefield removals and destruction evidence consistent. A
destroyed model cannot retain living movement eligibility without a location.
The existing fail-closed movement-location validation remains mandatory.

The regression reproduces the failure from the canonical loaded/unloaded reserve
session by submitting ordinary public decisions through round three. No edited
historical checkpoint is needed to reach the failure. Source policy and deadline
selection remain those recorded in [Order 64](ORDER_64_SCOPE_PLAN.md); its offline
source generator remains reproducible.

The owning path is the shared lifecycle boundary through
`reserve_lifetime_boundary.resolve_boundary`, reserve destruction resolution,
and the engine-owned destruction application. The application must use the
existing no-reaction model-death authority before recording physical removal.
Carrier and cargo follow their existing reserve route. Existing ingress and
repositioning exemptions and independent final-turn cleanup retain their meaning.

The original application is extracted from the oversized `GameState` module into
the existing reserve lifetime owner. It skips logical re-destruction of previously
dead members while retaining their removal lineage. The primary physical-history
consumer also reconstructs zero wounds from the existing reserve-death evidence;
its previous preserve-wounds override otherwise rejected the repaired legal state
on the next public submission. Reconstruction ordering and algorithms are unchanged.

Fight's reverse model history consumes the same existing authenticated reserve
unit-destruction event. That timeline otherwise cannot reverse logical death after
a prior casualty activates Fight-history validation. The mapping reads canonical
historical membership and earlier death/restoration mutations, preserving already
dead members when reversing the deadline. The canonical pre-deadline attached
fixture already passes restore; the added regression follows public play to the
deadline and checks subsequent restore and exact replay.

The bug-class search checked the shared unplaced-destruction primitive, empty
Dedicated Transport cleanup, reserve removal and primary reconstruction consumers.
Empty Dedicated Transport cleanup already uses the shared primitive. End-turn
coherency cleanup has separate removal semantics and remains a follow-up candidate;
this repair does not claim a demonstrated normal-play defect or fix for that path.

## Scope and contract

The existing [adapter contract](ADAPTER_DECISION_CONTRACT.md#order-64-reserve-and-ingress-lifetimes-contract-30)
covers automatic reserve destruction, movement selection, reserve terminal state
and exact-runtime persistence/replay. This repair adds no player-facing choice,
proposal family, event payload field, visibility rule or persistence schema.
Generated runtime identity and contract examples are refreshed by the standard
generators. Old checkpoints retain their exact-runtime requirement.

Issues 532 and 533 and coordinated hand-edited-history hardening remain separate
under the [sequential review policy](SEQUENTIAL_REMEDIATION_REVIEW_POLICY.md).
The default performance evidence is the exact-base assessment and current serial
smoke; this repair makes no full-game performance claim.

## Historical evidence

Order 97 pins the complete original reserve-lifetime test module. Its original
14,378 bytes and SHA-256
`93853589f0f45bd115d87ca6ef07467af5442b7ad8822e08c8683c973b15ea2e`
are retained at
`data/source_audits/issue534/baseline/tests/unit/test_order64_reserve_lifetimes.py.txt`.
The fixed-hash mapping records both the original reviewed revision and this PR's
exact main base, which contain identical bytes. The original manifest, assertion
receipts and file pin remain unchanged. The shared offline resolver rejects a
missing or corrupt archive or mapping.

This archive authenticates historical evidence. Current behavior is exercised by
the live regression suite, including public continuation, surviving unit actions,
both viewers, valid restore, fork and replay. Complete correctness, quality,
coverage, type, contract, source and required CI gates remain delivery obligations.
