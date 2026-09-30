# Order 101 / P03F — failed move-type setup selection

C03-06 left a unit selected to move after a complete setup failed. The only
pending choice was another placement submission, so an impossible setup trapped
the phase. Order 97 reproduced this with a 100-inch circular cargo base on the
60 by 44-inch battlefield.

## Source and obligations

The complete selected Game Datamissions observation is already retained in
`data/source_audits/order97/selected-sources.json`. It is the unversioned body
observed for Orders 84 and 97, under the maintained App-mirror source policy.
No new source observation, provider, or runtime source package is claimed.

| Clause | Obligation |
|---|---|
| 03.02-obligation-04 | A failed complete setup leaves the entire unit at its prior location. |
| 03.02.01-obligation-01 | A unit returned after failed move-type setup has not been selected to move. |
| 03.02.01-obligation-02 | It may be selected later, attempt another setup, or Remain Stationary. |

The selected `03.02.01` row is `rule:03:03.02.01:1`, fingerprint
`28bc62101a93e202a54e55347fd55736350d1afd0fb33eec725ee818b01d48e8`.
The shared engine rollback receipt references that immutable audit observation.
The retained negative probe and its JSON remain historical discovery evidence.

## Shared authority and bounded scope

The existing placement validation never commits a partial invalid placement.
After a well-formed rule-invalid ordinary move-type setup, the shared placement
owner cancels only the unresolved active movement selection. Battlefield poses,
cargo, reserves, completed selections and movement-distance records remain
unchanged. Disembark modes and reserve Ingress use the same rollback.

The pending request becomes the existing `select_movement_unit` authority. The
player can select another legal unit or reselect the failed one and use the
ordinary `select_movement_action` options, including legal Remain Stationary or
another setup. Every attempt receives fresh selection, action and proposal IDs.
Malformed, stale and context-drift submissions retain their existing pre-record
atomic rejection, with no cancelled selection. The separate Combat Disembark
diagnostic that Tactical placement is available does not establish failed setup;
it retains the existing Tactical/Combat proposal retry.

This search also covered deployment, destroyed-Transport emergency placement,
Stratagem/reaction ingress, revival, and return-to-battlefield consumers. They do
not consume an ordinary Movement-phase selection through this placement owner,
so this order does not give them ordinary movement eligibility or undo their
mandatory continuations.

`movement_setup_failed` binds the invalid-placement event and both recorded
selection/proposal decisions to before/after movement authority. Restore checks
the source pin, decision identities, rollback and later explicit reselection.
Shared adapter redaction removes internal movement snapshots from public events.
Restore derives the complete selected/completed/active selection projection from
ordered selection and activation-ending events, including their witness-derived
distance records. A receipt cannot erase another completed activation or reuse
superseded selection, action or rejection authority. Each linked decision needs
its exact request and recorded event, correct actor and phase context, and causal
order. Tactical setup, mandatory destroyed-Transport placement, and reactive
ingress retain their own completion classification.
Rejected attempts retain the same engine source authority as successful setup.
Reserve failures share request/context, diagnostic and source-chain validation
with arrivals, and bind carried ReserveState to the lifecycle owner's authenticated
historical entry inventory. Disembark closes its distinct initial and retained
Tactical-available retry schemas, physical army/model lineage, typed diagnostic,
and causal predecessor order. Canonical outer decisions must match their nested
proposals. Snapshot restore authenticates historical source events; replay
re-execution additionally recomputes physical request context.

Existing decision and proposal shapes remain in use; the adapter contract records
the changed continuation and the new audit event. Runtime identity and external
contract examples must be regenerated.

## Validation evidence and remaining merge gates

The frozen runtime is
`warhammer40k-core-v2:runtime-tree-sha256-v1:00e0dca239f06843d109d1591ffab12b5f8844e801e5005f4d4f778c6afd09e3`.
The 56 Order 101 cases and affected real consumers pass: the focused gate has
276 passes. The complete covered behavioral invocation has 10,160 passes, zero
errors/failures/skips, and 18 complete successful worker records. It took 771.10
seconds. Its initial coverage report failed to open the combined database;
separate coverage report/XML commands recovered the unchanged saved branch data
and passed the unchanged gate at 85.1927209112%. Raw failed-command evidence is
preserved; no additional behavioral run was made for recovery or shard profiling.
All 3,013 frozen production file hashes matched during recovery. The same
successful JUnit supplies the complete eight-shard manifest profile, labeled as
an uncommitted local Mac working tree, its base and runtime identity. It is not
presented as a hosted Linux profile or as an already committed head.

Full Ruff/format, mypy, pyright, all 11 import boundaries, generated identity and
external contract, pinned-base compatibility, TypeScript client/unit/conformance
and installed-wheel smoke gates pass. Serial performance completed without
coverage or competing test/build workers: 21 Order 101 samples took 36.51 seconds,
and all 27 inherited commands took 359.57 seconds. Baselines and numeric budgets
remain unchanged; the Mac is provisional reference hardware. The first full
quality run had 795 passes and a stale AST audit target after extracting the
shared reserve validator. The audit now requires living-component authority in
that shared validator and requires both accepted/rejected consumers to call it.
This test-only repair leaves the frozen runtime unchanged. The independent audit
repair review and its four deliberate ownership/delegation-removal probes pass.
The repaired complete quality gate passes all 796 tests, including inherited
performance budgets; pre-commit also passes.

Independent preliminary coding findings about erased completed selections,
superseded action/rejection authority, and rejected physical/source/context
history were repaired and independently reprobed. A clean preliminary repair
review is not final-head approval. A fresh independent exact-head coding review,
parent Astra audit, every required CI quality/generated/contract gate, both type
checkers, all eight behavioral shards, and combined branch coverage >=85% remain
required before merge. Draft-skipped checks are not passes. Core categories
01–25, faction behavior and complete-game performance are not certified here.
