# R34-002 sequence-origin repair

PR: https://github.com/SobolGaming/Warhammer_40k_AI/pull/438
Base: `e56c1a4caf2a6915548222caed0872627f8dbf43`.
Reviewed head: `1ea77b9697e0edc94a0edb4d7d694ea904c0af19`.
[Independent finding](https://github.com/SobolGaming/Warhammer_40k_AI/pull/438#discussion_r3974026147).
R34-001 and R34-003 remain independently closed. R34-002 requires exact-head
independent re-review after this correction. No merge or Order 34 closure is claimed.

## Invariant and reproduction

A completed shot retains its Action prohibition until its actual phase ends.
An asserted attack kind, sequence ID or model list cannot exclude a completion
from authentication. The prior implementation filtered history before binding
its origin; changing both kind and sequence hid a completion while leaving the
accepted shooting declaration looking like an unfinished executor prefix.

The new Normal and Snap regressions reproduced this defect on 1ea77b96: both
failed with DID NOT RAISE after renaming participation/completion together,
labelling them fight, and removing the matching completed-shooting effect.
All accepted declarations, decision records, ranged activations, model ownership,
actual timing and ordinary shot state were unchanged. Untouched JSON restoration
still reported `mission_action_unit_already_shot` before each mutation.

## Repair and scope audit

The existing model-attack history owner now authenticates the complete event
inventory before classification. Every participation matches its preceding
accepted shooting, out-of-phase shooting or melee declaration. Every executor
completion/resolved boundary needs that declaration and participation; orphan
and duplicate completion identities fail closed. No asserted kind, model list
or sequence ID selects which events reach this validation.

Melee classification additionally binds to its original typed request/result,
exact preceding decision ledger closure, proposal, game, round and deterministic
sequence identity. A fabricated melee declaration cannot establish a different
origin for completed shooting. Genuine melee and accepted unfinished executors
remain valid. Ordinary already-shot state stays independently enforced.

The bug-class search covered all `MODELS_ATTACKED_EVENT_TYPE` and completion
consumers. Historical Action-request reconstruction had a related subject filter
and now validates its whole prior event prefix through the same shared owner.
Retained-subject history validation reuses the same implementation and preserves
its specific subject query; complete lifecycle restoration always authenticates
the unfiltered inventory before accepting the state. Live eligibility reads the
existing indexed effects and does not scan history.

Only two production modules change: `model_attack_history.py` and
`activity_restriction_history.py`. No new ledger, decision, public payload shape,
source package, runtime hook, cache or architecture boundary is added. Generated
runtime/contract identities are refreshed and the existing adapter contract
explicitly states the provenance requirement. No behavioral test file is added,
deleted or renamed; shard membership is unchanged.

The Normal/Snap matrix covers 30 corruptions per route: fight/movement labels
with original or renamed sequences, a renamed shooting-kind control,
unchanged/empty/foreign models, and removed/retained effects. The real retained
melee path restores every partial checkpoint and rejects coordinated declaration/
participation changes to sequence, models, active player, game, round, phase and
request authority. Orphan and duplicate completions are tested from real events.
The static audit requires unfiltered history validation before classification
and shared use by historical Action reconstruction.

## Validation status

The initial focused gate passed 41 tests, and the broader Fight/retained gate
passed 157. Full final validation and fresh comparable performance are pending
at the initial local candidate freeze. The final evidence commit will replace
this status with actual results; this is not a merge-readiness claim.
